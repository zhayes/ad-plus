"""Persisted background jobs (renders today, previews later).

MCP owns the job: it writes progress, the backend only flips
``cancel_requested`` so there is a single writer per field.
"""

from __future__ import annotations

import os
import time
from typing import Any

from adplus import agent_bridge

KIND = "jobs"


def start(kind: str, project_id: str, **fields: Any) -> dict[str, Any]:
    job = {
        "id": agent_bridge.new_id("j"),
        "project_id": project_id,
        "kind": kind,
        "status": "running",
        "progress": 0.0,
        "frames_done": 0,
        "frames_total": int(fields.pop("frames_total", 0) or 0),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "finished_at": None,
        "pid": None,
        "output": None,
        "error": None,
        "cancel_requested": False,
        "log_tail": [],
        **fields,
    }
    agent_bridge.write_record(KIND, project_id, job)
    return job


def get(project_id: str, job_id: str) -> dict[str, Any] | None:
    return agent_bridge.read_record(KIND, project_id, job_id)


def update(job: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """Write progress without losing the backend's cancel flag.

    The runner owns the job dict in memory; the backend owns
    ``cancel_requested`` on disk. A naive write would clobber the flag on the
    very next progress tick, so merge it from disk first.
    """
    on_disk = agent_bridge.read_record(KIND, job["project_id"], job.get("id") or "")
    if on_disk and on_disk.get("cancel_requested") and not fields.get("cancel_requested"):
        job["cancel_requested"] = True
    if on_disk and "cancel_requested" in fields and not fields["cancel_requested"]:
        fields.pop("cancel_requested", None)
    job.update(fields)
    agent_bridge.write_record(KIND, job["project_id"], job)
    return job


def finish(job: dict[str, Any], status: str, error: str | None = None,
           output: str | None = None) -> dict[str, Any]:
    return update(
        job,
        status=status,
        progress=1.0 if status == "done" else job.get("progress", 0.0),
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        error=error,
        output=output or job.get("output"),
    )


def request_cancel(project_id: str, job_id: str) -> dict[str, Any]:
    """Called by the backend; keeps every other field untouched."""
    job = get(project_id, job_id)
    if job is None:
        raise KeyError(job_id)
    if job.get("status") == "running":
        job["cancel_requested"] = True
        agent_bridge.write_record(KIND, project_id, job)
    return job


def cancel_requested(project_id: str, job_id: str) -> bool:
    job = get(project_id, job_id)
    return bool(job and job.get("cancel_requested"))


def list_jobs(project_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    if project_id:
        rows = agent_bridge.list_records(KIND, project_id, limit=limit)
    else:
        rows = []
        for project in agent_bridge.PROJECTS_DIR.iterdir() if agent_bridge.PROJECTS_DIR.is_dir() else []:
            if project.is_dir():
                rows.extend(agent_bridge.list_records(KIND, project.name, limit=limit))
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows[:limit]


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def recover_interrupted() -> int:
    """Mark jobs whose process vanished as interrupted (called on startup)."""
    changed = 0
    for job in list_jobs(limit=200):
        if job.get("status") != "running":
            continue
        if _pid_alive(job.get("pid")):
            continue
        job["status"] = "interrupted"
        job["error"] = "app restarted while this job was running"
        job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        agent_bridge.write_record(KIND, job["project_id"], job)
        changed += 1
    return changed
