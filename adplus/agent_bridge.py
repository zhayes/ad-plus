"""Filesystem contract between the Pi MCP tools, the backend and the UI.

Three processes take part in a run: Pi (which hosts our MCP server), the
FastAPI backend, and the WebView. They cannot call each other directly, so
records live on disk and each side polls the files it cares about:

    projects/<id>/quotes/<quote_id>.json
    projects/<id>/approvals/<approval_id>.json
    projects/<id>/jobs/<job_id>.json

Every write is tmp-file + ``os.replace()`` so a reader never sees half a JSON.
Only the writer of a record mutates it: the MCP tool creates and finalises,
the backend only appends a ``decision`` / ``cancel_requested`` field.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from adplus.paths import PROJECTS as PROJECTS_DIR

KINDS = ("quotes", "approvals", "jobs")
DECIDED = ("approved", "rejected", "timeout")


def new_id(prefix: str) -> str:
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def kind_dir(kind: str, project_id: str, create: bool = True) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown record kind {kind!r}")
    path = PROJECTS_DIR / project_id / kind
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def record_path(kind: str, project_id: str, record_id: str) -> Path:
    return kind_dir(kind, project_id).parent / kind / f"{record_id}.json"


def write_record(kind: str, project_id: str, record: dict[str, Any]) -> Path:
    """Atomically persist a record (tmp file in the same dir + replace)."""
    target = record_path(kind, project_id, str(record["id"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def read_record(kind: str, project_id: str, record_id: str) -> dict[str, Any] | None:
    path = record_path(kind, project_id, record_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_records(
    kind: str,
    project_id: str,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    directory = kind_dir(kind, project_id, create=False)
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if status is None or record.get("status") == status:
            rows.append(record)
    return rows


def decide(
    kind: str,
    project_id: str,
    record_id: str,
    status: str,
    comment: str = "",
    by: str = "user",
) -> dict[str, Any]:
    """Apply a human decision (called by the backend, never by the MCP tool)."""
    record = read_record(kind, project_id, record_id)
    if record is None:
        raise KeyError(record_id)
    if record.get("status") != "pending":
        return record
    record["status"] = status
    record["decision"] = {
        "by": by,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "comment": comment,
    }
    write_record(kind, project_id, record)
    return record


def wait_for_decision(
    kind: str,
    project_id: str,
    record_id: str,
    timeout_seconds: float = 900,
    interval: float = 0.5,
) -> dict[str, Any]:
    """Block until the UI decides (or the timeout fires).

    The tool call blocks on purpose: the agent must not spend money or move to
    the next stage while a human is still looking at the quote / storyboard.
    """
    deadline = time.time() + max(1.0, timeout_seconds)
    while time.time() < deadline:
        record = read_record(kind, project_id, record_id)
        if record and record.get("status") in DECIDED:
            return record
        time.sleep(interval)
    record = read_record(kind, project_id, record_id) or {"id": record_id, "project_id": project_id}
    if record.get("status") == "pending":
        record["status"] = "timeout"
        record["decision"] = {
            "by": "system",
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "comment": f"no response within {int(timeout_seconds)}s",
        }
        write_record(kind, project_id, record)
    return record


def pending(kind: str, project_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Pending records across one project, or across all projects."""
    if project_id:
        return list_records(kind, project_id, status="pending", limit=limit)
    root = Path(PROJECTS_DIR)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for project in root.iterdir():
        if project.is_dir():
            rows.extend(list_records(kind, project.name, status="pending", limit=limit))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]
