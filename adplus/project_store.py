"""Project / version / shot / brand store for Ad+ P0.

The filesystem is the contract (same rule as ``agent_bridge``): the backend,
the MCP tools and the UI all read and write JSON under ``projects/<id>/`` and
``brands/<id>.json``. Every write is atomic (tmp file + ``os.replace``).

Layout added in this module::

    projects/<id>/project.json              # v2 marker (status, platform, brief…)
    projects/<id>/versions/<vid>.json        # shots[] + brand_snapshot
    brands/<brand_id>.json                   # cross-project brand kit

Design rules
------------
* ``shots[]`` array order is the storyboard order; ``index`` mirrors it.
* Reordering / adding / deleting recomputes ``start_s`` / ``end_s``; durations
  are preserved.
* A version snapshots the brand at creation time. Editing a brand never
  rewrites an existing version.
* Old ``project.json`` (v1) is normalised on read; it is only written back on
  the first real mutation.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from adplus.paths import BRANDS, PROJECTS

PROJECT_STATUSES = (
    "draft", "briefing", "quoted", "storyboard", "producing", "review", "delivered", "archived",
)
VERSION_STATUSES = ("draft", "producing", "review", "approved", "superseded")
SHOT_ROLES = ("hook", "build", "proof", "cta")
SHOT_STATUSES = ("planned", "generating", "ready", "approved", "needs_rework")
PRODUCTION_METHODS = (
    "source_video", "image_to_video", "reference_to_video", "avatar",
    "lip_sync", "motion_graphic", "still_plate", "product_composite",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _check_id(value: str, label: str = "id") -> str:
    value = (value or "").strip()
    if not _ID_RE.match(value):
        raise ValueError(f"{label} must match {_ID_RE.pattern}")
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("type", "name", "label", "text"):
            if value.get(key):
                return str(value[key])
    return json.dumps(value, ensure_ascii=False)


def _workspace_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECTS.parent.resolve()))
    except (ValueError, OSError):
        return str(path)


def _project_dir(project_id: str) -> Path:
    return PROJECTS / _check_id(project_id, "project_id")


def _versions_dir(project_id: str, create: bool = False) -> Path:
    path = _project_dir(project_id) / "versions"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------------- #
def _has_render(project_id: str) -> bool:
    root = PROJECTS / project_id / "renders"
    if not root.is_dir():
        return False
    return any(p.suffix.lower() in {".mp4", ".mov", ".webm"} for p in root.rglob("*") if p.is_file())


def _normalise_project(data: dict[str, Any], project_id: str) -> dict[str, Any]:
    project = copy.deepcopy(data)
    project["version"] = "2.0"
    project["project_id"] = project_id
    project["id"] = project_id
    project.setdefault("title", project_id)
    status = project.get("status")
    if status not in PROJECT_STATUSES:
        status = "review" if _has_render(project_id) else "draft"
    project["status"] = status
    project.setdefault("pipeline_type", "cinematic")
    project.setdefault("platform", "generic")
    project.setdefault("aspect", "9:16")
    project.setdefault("duration_s", 15)
    project.setdefault("quality_tier", "standard")
    project.setdefault("brand_id", None)
    project.setdefault("persona_id", None)
    project.setdefault("format_id", None)
    project.setdefault("product_id", None)
    project.setdefault("brief", {})
    project.setdefault("current_version_id", None)
    project.setdefault("cover", None)
    project.setdefault("created_at", _now())
    project.setdefault("updated_at", project["created_at"])
    return project


def load_project(project_id: str) -> dict[str, Any] | None:
    path = _project_dir(project_id) / "project.json"
    data = _read_json(path)
    if data is None:
        return None
    return _normalise_project(data, project_id)


def save_project(project: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(project)
    project_id = _check_id(str(project.get("project_id") or ""), "project_id")
    project["version"] = "2.0"
    project["id"] = project_id
    project["updated_at"] = _now()
    _atomic_json(PROJECTS / project_id / "project.json", project)
    return project


def new_project_id(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:40] or "project"
    return f"{base}-{uuid.uuid4().hex[:4]}"


def create_project(
    title: str,
    project_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("title required")
    project_id = _check_id(project_id or new_project_id(title), "project_id")
    root = PROJECTS / project_id
    if root.exists():
        raise FileExistsError(project_id)
    for name in ("artifacts", "assets", "renders", "versions"):
        (root / name).mkdir(parents=True, exist_ok=True)
    project = {
        "version": "2.0",
        "project_id": project_id,
        "title": title,
        "status": fields.get("status") or "draft",
        "pipeline_type": fields.get("pipeline_type") or fields.get("pipeline") or "cinematic",
        "platform": fields.get("platform") or "douyin",
        "aspect": fields.get("aspect") or "9:16",
        "duration_s": float(fields.get("duration_s") or 15),
        "quality_tier": fields.get("quality_tier") or "standard",
        "brand_id": fields.get("brand_id"),
        "persona_id": fields.get("persona_id"),
        "product_id": fields.get("product_id"),
        "format_id": fields.get("format_id"),
        "route": copy.deepcopy(fields.get("route")),
        "brief": copy.deepcopy(fields.get("brief") or {}),
        "current_version_id": None,
        "cover": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    return save_project(project)


def update_project(project_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    project = load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    allowed = {
        "title", "status", "platform", "aspect", "duration_s", "quality_tier",
        "brand_id", "persona_id", "product_id", "format_id", "brief", "current_version_id", "pipeline_type", "cover", "route",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown project fields: {sorted(unknown)}")
    if "title" in fields and not str(fields["title"]).strip():
        raise ValueError("title required")
    if "status" in fields and fields["status"] not in PROJECT_STATUSES:
        raise ValueError(f"status must be one of {PROJECT_STATUSES}")
    if "duration_s" in fields and float(fields["duration_s"]) <= 0:
        raise ValueError("duration_s must be positive")
    if "brand_id" in fields and fields["brand_id"]:
        if load_brand(str(fields["brand_id"])) is None:
            raise ValueError("brand not found")
    project.update(copy.deepcopy(fields))
    if project.get("current_version_id"):
        if load_version(project_id, str(project["current_version_id"])) is None:
            raise ValueError("version not found")
    return save_project(project)


def latest_render(project_id: str) -> dict[str, Any] | None:
    root = PROJECTS / project_id / "renders"
    if not root.is_dir():
        return None
    files = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".webm"}
        and ".qa" not in str(p) and "final_review" not in str(p)
    ]
    if not files:
        return None
    path = max(files, key=lambda p: p.stat().st_mtime)
    return {"path": _workspace_rel(path), "bytes": path.stat().st_size, "mtime": path.stat().st_mtime}


def _cover_for(project: dict[str, Any], current: dict[str, Any] | None) -> str | None:
    if project.get("cover"):
        return str(project["cover"])
    if current:
        render = current.get("render") or {}
        if render.get("poster"):
            return str(render["poster"])
        if render.get("path"):
            return str(render["path"])
    render = latest_render(project["project_id"])
    return str(render["path"]) if render else None


def pending_records(project_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = PROJECTS / project_id
    for kind in ("quotes", "approvals"):
        directory = root / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            record = _read_json(path)
            if record and record.get("status") == "pending":
                rows.append({**record, "kind": kind})
    return rows


def pending_count(project_id: str) -> int:
    return len(pending_records(project_id))


def project_summary(project: dict[str, Any]) -> dict[str, Any]:
    project_id = str(project["project_id"])
    versions = list_versions(project_id)
    current_id = project.get("current_version_id")
    current = next((v for v in versions if v["id"] == current_id), None)
    if current is None and versions:
        current = versions[0]
    cost = sum(float(v.get("cost_usd") or 0) for v in versions)
    try:
        updated = (PROJECTS / project_id / "project.json").stat().st_mtime
    except OSError:
        updated = 0.0
    try:
        from adplus import production
        prod = production.production_payload(project_id)
        stage_label = next((item["label"] for item in (prod or {}).get("stages", []) if item["id"] == (prod or {}).get("current_stage")), "")
        next_action = (prod or {}).get("next_action") or ""
        route_label = ((prod or {}).get("route") or {}).get("label") or ""
    except Exception:
        stage_label, next_action, route_label = "", "", ""
    return {
        "id": project_id,
        "title": project.get("title") or project_id,
        "status": project.get("status") or "draft",
        "platform": project.get("platform") or "generic",
        "aspect": project.get("aspect") or "9:16",
        "duration_s": project.get("duration_s") or 15,
        "quality_tier": project.get("quality_tier") or "standard",
        "cover": _cover_for(project, load_version(project_id, current["id"]) if current else None),
        "updated": updated,
        "updated_at": project.get("updated_at"),
        "version_count": len(versions),
        "current_version": current["id"] if current else None,
        "current_version_label": current.get("label") if current else None,
        "pending_count": pending_count(project_id),
        "cost_usd": round(cost, 4),
        "brand_id": project.get("brand_id"),
        "route_label": route_label,
        "stage_label": stage_label,
        "next_action": next_action,
    }


def list_projects() -> list[dict[str, Any]]:
    if not PROJECTS.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for entry in PROJECTS.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        project = load_project(entry.name)
        if project is None:
            continue
        rows.append(project_summary(project))
    rows.sort(key=lambda r: r.get("updated") or 0, reverse=True)
    return rows


# --------------------------------------------------------------------------- #
# versions + shots
# --------------------------------------------------------------------------- #
def _version_path(project_id: str, version_id: str) -> Path:
    return _versions_dir(project_id) / f"{_check_id(version_id, 'version_id')}.json"


def _next_version_number(project_id: str) -> int:
    numbers = []
    directory = _versions_dir(project_id)
    if directory.is_dir():
        for path in directory.glob("*.json"):
            match = re.fullmatch(r"v(\d+)", path.stem)
            if match:
                numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def version_summary(version: dict[str, Any]) -> dict[str, Any]:
    shots = version.get("shots") or []
    duration = round(sum(float(s.get("duration_s") or 0) for s in shots), 3)
    return {
        "id": version.get("id"),
        "label": version.get("label") or version.get("id"),
        "status": version.get("status") or "draft",
        "created_at": version.get("created_at"),
        "shots_count": len(shots),
        "duration_s": duration or version.get("duration_s") or 0,
        "cost_usd": version.get("cost_usd") or 0,
        "render": version.get("render"),
        "has_review": bool(version.get("review")),
        "brand": (version.get("brand_snapshot") or {}).get("name"),
    }


def load_version(project_id: str, version_id: str) -> dict[str, Any] | None:
    return _read_json(_version_path(project_id, version_id))


def list_versions(project_id: str) -> list[dict[str, Any]]:
    directory = _versions_dir(project_id)
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        version = _read_json(path)
        if version is None:
            continue
        rows.append(version_summary(version))
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def save_version(version: dict[str, Any]) -> dict[str, Any]:
    project_id = _check_id(str(version.get("project_id") or ""), "project_id")
    version_id = _check_id(str(version.get("id") or ""), "version_id")
    version = copy.deepcopy(version)
    version["project_id"] = project_id
    version["id"] = version_id
    shots = recompute_timeline(version.get("shots") or [])
    version["shots"] = shots
    version["duration_s"] = round(sum(float(s["duration_s"]) for s in shots), 3)
    _atomic_json(_version_path(project_id, version_id), version)
    return version


def normalise_shot(raw: dict[str, Any]) -> dict[str, Any]:
    """Additive shot contract; old versions stay readable.

    ``production_method`` is the bridge between the storyboard and the model
    registry.  ``asset_refs`` binds a shot to a presenter/product asset instead
    of relying on a prompt to guess which image is which.
    """
    shot = copy.deepcopy(raw)
    method = str(shot.get("production_method") or "source_video")
    shot["production_method"] = method if method in PRODUCTION_METHODS else "source_video"
    for key in ("shot_language", "asset_refs", "generation_spec", "timeline"):
        value = shot.get(key)
        shot[key] = value if isinstance(value, dict) else {}
    if shot.get("persona_id") is not None:
        shot["persona_id"] = str(shot.get("persona_id"))
    if shot.get("product_id") is not None:
        shot["product_id"] = str(shot.get("product_id"))
    return shot


def recompute_timeline(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep each shot's duration, rebuild index/start/end in array order."""
    out: list[dict[str, Any]] = []
    cursor = 0.0
    for index, raw in enumerate(shots, start=1):
        shot = normalise_shot(raw)
        duration = shot.get("duration_s")
        if duration is None:
            duration = float(shot.get("end_s") or 0) - float(shot.get("start_s") or 0)
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = 0.0
        duration = max(0.2, round(duration or 2.5, 3))
        shot["index"] = index
        shot["start_s"] = round(cursor, 3)
        shot["end_s"] = round(cursor + duration, 3)
        shot["duration_s"] = duration
        cursor += duration
        out.append(shot)
    return out


def ensure_version(project_id: str) -> dict[str, Any] | None:
    """Return the current version, bootstrapping v1 from scene_plan.json once."""
    versions = list_versions(project_id)
    project = load_project(project_id)
    if project is None:
        return None
    if versions:
        current_id = project.get("current_version_id")
        current = next((v for v in versions if v["id"] == current_id), None)
        if current:
            return load_version(project_id, current["id"])
        return load_version(project_id, versions[0]["id"])

    scene_path = PROJECTS / project_id / "artifacts" / "scene_plan.json"
    payload = _read_json(scene_path)
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return None

    shots: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        start = float(scene.get("start_seconds", scene.get("start_s", 0)) or 0)
        end = float(scene.get("end_seconds", scene.get("end_s", 0)) or 0)
        duration = (end - start) if end > start else float(scene.get("duration_s") or 2.5)
        preview = scene.get("preview") or scene.get("preview_path")
        shots.append({
            "id": str(scene.get("id") or f"s{index + 1}"),
            "role": _role_for(scene, index, len(scenes)),
            "description": _text(scene.get("description") or scene.get("note") or scene.get("summary")),
            "framing": _text(scene.get("framing")),
            "movement": _text(scene.get("movement")),
            "transition_in": _text(scene.get("transition_in")),
            "transition_out": _text(scene.get("transition_out")),
            "on_screen_text": _text(scene.get("on_screen_text") or scene.get("text")),
            "narration": _text(scene.get("narration") or scene.get("voiceover")),
            "status": "ready" if preview else "planned",
            "locked": False,
            "preview": str(preview) if preview else None,
            "take_count": 0,
            "cost_usd": 0,
            "duration_s": max(0.2, round(duration, 3)),
        })
    if not shots:
        return None

    version = {
        "id": "v1",
        "label": "V1",
        "project_id": project_id,
        "status": "review" if latest_render(project_id) else "draft",
        "parent_id": None,
        "created_at": _now(),
        "render": latest_render(project_id),
        "shots": recompute_timeline(shots),
        "cost_usd": 0,
        "review": None,
        "brand_snapshot": brand_snapshot(project.get("brand_id")),
    }
    save_version(version)
    project["current_version_id"] = "v1"
    save_project(project)
    return load_version(project_id, "v1")


def _role_for(scene: dict[str, Any], index: int, total: int) -> str:
    if index == 0:
        return "hook"
    if index == total - 1:
        return "cta"
    raw = str(scene.get("narrative_role") or scene.get("role") or "").lower()
    if "proof" in raw or "demo" in raw or "product" in raw:
        return "proof"
    return "build"


def create_version(
    project_id: str,
    label: str | None = None,
    parent_id: str | None = None,
    copy_shots: bool = True,
) -> dict[str, Any]:
    project = load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    parent: dict[str, Any] | None = None
    if parent_id:
        parent = load_version(project_id, parent_id)
        if parent is None:
            raise ValueError("parent version not found")
    elif project.get("current_version_id"):
        parent = load_version(project_id, str(project["current_version_id"]))
    if parent is None:
        versions = list_versions(project_id)
        if versions:
            parent = load_version(project_id, versions[0]["id"])

    number = _next_version_number(project_id)
    version = {
        "id": f"v{number}",
        "label": label or f"V{number}",
        "project_id": project_id,
        "status": "draft",
        "parent_id": parent.get("id") if parent else None,
        "created_at": _now(),
        "render": None,
        "shots": copy.deepcopy(parent.get("shots") or []) if (parent and copy_shots) else [],
        "cost_usd": 0,
        "review": None,
        "brand_snapshot": brand_snapshot(project.get("brand_id")),
    }
    save_version(version)
    project["current_version_id"] = version["id"]
    save_project(project)
    return load_version(project_id, version["id"]) or version


def set_current_version(project_id: str, version_id: str) -> dict[str, Any]:
    if load_version(project_id, version_id) is None:
        raise FileNotFoundError(version_id)
    project = load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    project["current_version_id"] = version_id
    save_project(project)
    return project


def update_version(project_id: str, version_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    allowed = {"status", "label", "render", "review", "cost_usd"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown version fields: {sorted(unknown)}")
    if "status" in fields and fields["status"] not in VERSION_STATUSES:
        raise ValueError(f"status must be one of {VERSION_STATUSES}")
    version.update(copy.deepcopy(fields))
    return save_version(version)


def reorder_shots(project_id: str, version_id: str, order: list[str]) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    shots = version.get("shots") or []
    by_id = {str(s["id"]): s for s in shots}
    if len(order) != len(by_id) or set(order) != set(by_id):
        raise ValueError("order must contain every shot id exactly once")
    version["shots"] = recompute_timeline([by_id[sid] for sid in order])
    return save_version(version)


def _next_shot_id(shots: list[dict[str, Any]]) -> str:
    used = {str(s.get("id")) for s in shots}
    n = 1
    while f"s{n}" in used:
        n += 1
    return f"s{n}"


def add_shot(
    project_id: str,
    version_id: str,
    after_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    shots = list(version.get("shots") or [])
    shot = {
        "id": _next_shot_id(shots),
        "role": fields.get("role") if fields.get("role") in SHOT_ROLES else "build",
        "description": str(fields.get("description") or ""),
        "framing": str(fields.get("framing") or ""),
        "movement": str(fields.get("movement") or ""),
        "transition_in": str(fields.get("transition_in") or ""),
        "transition_out": str(fields.get("transition_out") or ""),
        "on_screen_text": str(fields.get("on_screen_text") or ""),
        "narration": str(fields.get("narration") or ""),
        "status": fields.get("status") if fields.get("status") in SHOT_STATUSES else "planned",
        "locked": bool(fields.get("locked") or False),
        "preview": fields.get("preview"),
        "take_count": 0,
        "cost_usd": 0,
        "duration_s": float(fields.get("duration_s") or 2.5),
        "production_method": fields.get("production_method") or "source_video",
        "shot_language": copy.deepcopy(fields.get("shot_language") or {}),
        "asset_refs": copy.deepcopy(fields.get("asset_refs") or {}),
        "generation_spec": copy.deepcopy(fields.get("generation_spec") or {}),
        "timeline": copy.deepcopy(fields.get("timeline") or {}),
        "persona_id": fields.get("persona_id"),
        "product_id": fields.get("product_id"),
        "format_id": fields.get("format_id"),
    }
    shot = normalise_shot(shot)
    if after_id:
        index = next((i for i, s in enumerate(shots) if str(s.get("id")) == after_id), None)
        if index is None:
            raise ValueError("after_id not found")
        shots.insert(index + 1, shot)
    else:
        shots.append(shot)
    version["shots"] = recompute_timeline(shots)
    return save_version(version)


def update_shot(
    project_id: str,
    version_id: str,
    shot_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    shots = list(version.get("shots") or [])
    index = next((i for i, s in enumerate(shots) if str(s.get("id")) == shot_id), None)
    if index is None:
        raise KeyError(shot_id)
    allowed = {
        "role", "description", "framing", "movement", "transition_in", "transition_out",
        "on_screen_text", "narration", "status", "locked", "preview", "duration_s",
        "take_count", "cost_usd", "production_method", "shot_language",
        "asset_refs", "generation_spec", "timeline", "persona_id", "product_id",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown shot fields: {sorted(unknown)}")
    if "role" in fields and fields["role"] not in SHOT_ROLES:
        raise ValueError(f"role must be one of {SHOT_ROLES}")
    if "status" in fields and fields["status"] not in SHOT_STATUSES:
        raise ValueError(f"status must be one of {SHOT_STATUSES}")
    if "production_method" in fields and fields["production_method"] not in PRODUCTION_METHODS:
        raise ValueError(f"production_method must be one of {PRODUCTION_METHODS}")
    shot = copy.deepcopy(shots[index])
    shot.update(copy.deepcopy(fields))
    if "duration_s" in fields:
        try:
            shot["duration_s"] = max(0.2, float(fields["duration_s"]))
        except (TypeError, ValueError):
            raise ValueError("duration_s must be a number")
    shots[index] = shot
    version["shots"] = recompute_timeline(shots)
    saved = save_version(version)
    return next(s for s in saved["shots"] if str(s["id"]) == shot_id)


def delete_shot(project_id: str, version_id: str, shot_id: str) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    shots = [s for s in (version.get("shots") or []) if str(s.get("id")) != shot_id]
    if len(shots) == len(version.get("shots") or []):
        raise KeyError(shot_id)
    # An empty storyboard is a valid draft: the editor shows its empty state
    # and the user can add a new shot. Stage approval still requires shots.
    version["shots"] = recompute_timeline(shots)
    return save_version(version)


def project_detail(project_id: str) -> dict[str, Any] | None:
    project = load_project(project_id)
    if project is None:
        return None
    ensure_version(project_id)
    project = load_project(project_id) or project
    versions = list_versions(project_id)
    current_id = project.get("current_version_id")
    if not current_id and versions:
        current_id = versions[0]["id"]
    current = load_version(project_id, str(current_id)) if current_id else None
    if current is not None:
        current = {**current, "shots_count": len(current.get("shots") or [])}
    if current and project.get("current_version_id") != current["id"]:
        project["current_version_id"] = current["id"]
        save_project(project)
    return {
        "project": project,
        "versions": versions,
        "current_version": current,
        "pending": pending_records(project_id),
        "brand": brand_snapshot(project.get("brand_id")),
        "latest_quote": latest_quote(project_id),
        "latest_review": latest_review(project_id, str(current["id"])) if current else None,
        "deliverables": list_deliverables(project_id)[:5],
    }


# --------------------------------------------------------------------------- #
# brands
# --------------------------------------------------------------------------- #
def _brands_dir(create: bool = False) -> Path:
    if create:
        BRANDS.mkdir(parents=True, exist_ok=True)
    return BRANDS


def _normalise_brand(data: dict[str, Any]) -> dict[str, Any]:
    brand = copy.deepcopy(data)
    brand.setdefault("id", f"b_{uuid.uuid4().hex[:8]}")
    brand.setdefault("name", "未命名品牌")
    brand.setdefault("logo", None)
    brand["colors"] = [str(c) for c in (brand.get("colors") or []) if str(c).strip()][:5]
    brand.setdefault("font_cn", "")
    brand.setdefault("font_en", "")
    brand["tone"] = [str(t) for t in (brand.get("tone") or []) if str(t).strip()]
    brand["voice"] = brand.get("voice") if isinstance(brand.get("voice"), dict) else {}
    brand["banned_words"] = [str(w) for w in (brand.get("banned_words") or []) if str(w).strip()]
    brand["default"] = bool(brand.get("default"))
    brand.setdefault("created_at", _now())
    brand["updated_at"] = _now()
    return brand


def list_brands() -> list[dict[str, Any]]:
    directory = _brands_dir()
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        brand = _read_json(path)
        if brand:
            rows.append(brand)
    rows.sort(key=lambda b: str(b.get("updated_at") or ""), reverse=True)
    rows.sort(key=lambda b: 0 if b.get("default") else 1)
    return rows


def load_brand(brand_id: str) -> dict[str, Any] | None:
    return _read_json(_brands_dir() / f"{_check_id(brand_id, 'brand_id')}.json")


def save_brand(data: dict[str, Any], brand_id: str | None = None) -> dict[str, Any]:
    existing = load_brand(brand_id) if brand_id else None
    brand = _normalise_brand({**(existing or {}), **copy.deepcopy(data)})
    if brand_id:
        brand["id"] = _check_id(brand_id, "brand_id")
    else:
        brand["id"] = f"b_{uuid.uuid4().hex[:8]}"
    if not str(brand.get("name") or "").strip():
        raise ValueError("brand name required")
    if brand["default"]:
        for other in list_brands():
            if other.get("id") != brand["id"] and other.get("default"):
                other["default"] = False
                _atomic_json(_brands_dir() / f"{other['id']}.json", other)
    _atomic_json(_brands_dir(create=True) / f"{brand['id']}.json", brand)
    return brand


def delete_brand(brand_id: str) -> bool:
    path = _brands_dir() / f"{_check_id(brand_id, 'brand_id')}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def set_default_brand(brand_id: str) -> dict[str, Any]:
    target = load_brand(brand_id)
    if target is None:
        raise FileNotFoundError(brand_id)
    for brand in list_brands():
        brand["default"] = brand.get("id") == brand_id
        brand["updated_at"] = _now()
        _atomic_json(_brands_dir(create=True) / f"{brand['id']}.json", brand)
    return load_brand(brand_id) or target


def apply_brand(project_id: str, brand_id: str) -> dict[str, Any]:
    if load_brand(brand_id) is None:
        raise FileNotFoundError(brand_id)
    project = load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    project["brand_id"] = brand_id
    return save_project(project)


def brand_snapshot(brand_id: str | None) -> dict[str, Any] | None:
    brand = load_brand(brand_id) if brand_id else None
    if brand is None:
        brand = next((b for b in list_brands() if b.get("default")), None)
    if brand is None:
        return None
    snapshot = copy.deepcopy(brand)
    snapshot["captured_at"] = _now()
    return snapshot




# --------------------------------------------------------------------------- #
# plan gate / review / deliverables
# --------------------------------------------------------------------------- #
CHECK_LABELS = {
    "technical_probe": "技术参数",
    "visual_spotcheck": "画面抽检",
    "audio_spotcheck": "声音",
    "promise_preservation": "承诺一致性",
    "subtitle_check": "字幕",
    "atelier": "原创性",
}

EXPORT_PRESETS = {
    "original": (0, 0),
    "douyin_1080": (1080, 1920),
    "xiaohongshu_1080": (1080, 1920),
    "preview_720": (720, 1280),
}


def _latest_json(directory: Path) -> dict[str, Any] | None:
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.json") if p.is_file()]
    if not files:
        return None
    path = max(files, key=lambda p: p.stat().st_mtime)
    return _read_json(path)


def latest_quote(project_id: str) -> dict[str, Any] | None:
    return _latest_json(PROJECTS / project_id / "quotes")


def latest_review(project_id: str, version_id: str) -> dict[str, Any] | None:
    return _read_json(PROJECTS / project_id / "reviews" / f"{version_id}.json")


def _keyframes(project_id: str, version: dict[str, Any] | None) -> list[str]:
    review_dir = PROJECTS / project_id / "review"
    if review_dir.is_dir():
        frames = sorted(
            (p for p in review_dir.glob("*.png") if p.is_file()),
            key=lambda p: p.name,
        )
        if frames:
            return [_workspace_rel(p) for p in frames[:3]]
    if version:
        previews = [str(shot["preview"]) for shot in version.get("shots") or [] if shot.get("preview")]
        if previews:
            return previews[:3]
        poster = (version.get("render") or {}).get("poster")
        if poster:
            return [str(poster)]
    return []


def plan_payload(project_id: str) -> dict[str, Any] | None:
    project = load_project(project_id)
    if project is None:
        return None
    version = ensure_version(project_id)
    proposal = _read_json(PROJECTS / project_id / "artifacts" / "proposal_packet.json")
    return {
        "project": project,
        "quote": latest_quote(project_id),
        "proposal": proposal,
        "keyframes": _keyframes(project_id, version),
        "version": version_summary(version) if version else None,
    }


def _brand_hits(version: dict[str, Any] | None) -> list[str]:
    if not version:
        return []
    brand = version.get("brand_snapshot") or {}
    words = [str(w).strip() for w in (brand.get("banned_words") or []) if str(w).strip()]
    if not words:
        return []
    text = " ".join(
        str(shot.get(field) or "")
        for shot in version.get("shots") or []
        for field in ("description", "on_screen_text", "narration")
    )
    return [word for word in words if word in text]


def review_payload(project_id: str, version_id: str | None = None) -> dict[str, Any] | None:
    project = load_project(project_id)
    if project is None:
        return None
    version = load_version(project_id, version_id) if version_id else ensure_version(project_id)
    if version is None:
        return None
    final = _read_json(PROJECTS / project_id / "artifacts" / "final_review.json")
    report = _read_json(PROJECTS / project_id / "artifacts" / "render_report.json")
    checks: list[dict[str, Any]] = []
    if final and isinstance(final.get("checks"), dict):
        for key, value in final["checks"].items():
            if not isinstance(value, dict):
                continue
            checks.append({
                "key": key,
                "label": CHECK_LABELS.get(key, key),
                "verdict": value.get("verdict") or "unknown",
                "detail": value.get("detail") or "",
                "note": value.get("note") or "",
            })
    hits = _brand_hits(version)
    if hits:
        checks.append({
            "key": "brand_compliance",
            "label": "品牌禁用词",
            "verdict": "fail",
            "detail": "命中：" + "、".join(hits),
            "note": "",
        })
    if hits:
        qa_status = "fail"
    elif final:
        verdicts = [c["verdict"] for c in checks]
        qa_status = "fail" if "fail" in verdicts else ("warn" if ("pass_with_note" in verdicts or "warn" in verdicts) else "pass")
    else:
        qa_status = "unknown" if (version.get("render") or {}).get("path") else "none"
    review = latest_review(project_id, str(version["id"]))
    return {
        "project": project,
        "version": version_summary(version),
        "final_review": final,
        "render_report": report,
        "review": review,
        "qa": {
            "status": qa_status,
            "checks": checks,
            "brand_hits": hits,
            "issues": (final or {}).get("issues_found") or [],
        },
    }


def save_review(
    project_id: str,
    version_id: str,
    approved: bool,
    decisions: list[dict[str, Any]] | None = None,
    comment: str = "",
    qa_status: str = "unknown",
) -> dict[str, Any]:
    if load_version(project_id, version_id) is None:
        raise FileNotFoundError(version_id)
    record = {
        "id": f"rev_{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "version_id": version_id,
        "status": "approved" if approved else "rejected",
        "approved": approved,
        "decisions": decisions or [],
        "comment": comment,
        "qa_status": qa_status,
        "created_at": _now(),
    }
    path = PROJECTS / project_id / "reviews" / f"{version_id}.json"
    _atomic_json(path, record)
    project = load_project(project_id)
    if project is not None:
        project["status"] = "delivered" if approved else "producing"
        save_project(project)
    return record


def list_deliverables(project_id: str) -> list[dict[str, Any]]:
    directory = PROJECTS / project_id / "deliverables"
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        record = _read_json(path)
        if record:
            rows.append(record)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return cleaned or "adplus-export"


def export_version(
    project_id: str,
    version_id: str,
    preset: str = "original",
    filename: str | None = None,
) -> dict[str, Any]:
    version = load_version(project_id, version_id)
    if version is None:
        raise FileNotFoundError(version_id)
    render = version.get("render") or {}
    render_path = render.get("path")
    if not render_path:
        raise ValueError("version has no render")
    source = (PROJECTS.parent / str(render_path)).resolve()
    if not source.is_file():
        raise FileNotFoundError(str(render_path))
    if preset not in EXPORT_PRESETS:
        raise ValueError(f"unknown preset {preset!r}")

    directory = PROJECTS / project_id / "deliverables"
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename(filename or f"{project_id}-{version.get('label') or version_id}-{preset}")
    if stem.lower().endswith(".mp4"):
        stem = stem[:-4]
    target = directory / f"{stem}.mp4"
    counter = 2
    while target.exists():
        target = directory / f"{stem}-{counter}.mp4"
        counter += 1

    width, height = EXPORT_PRESETS[preset]
    copied = False
    if width and height:
        ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        proc = subprocess.run(
            [
                ffmpeg, "-v", "error", "-y", "-i", str(source),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(target),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        copied = proc.returncode == 0 and target.is_file() and target.stat().st_size > 0
    if not copied:
        shutil.copy2(source, target)

    record = {
        "id": f"d_{uuid.uuid4().hex[:10]}",
        "project_id": project_id,
        "version_id": version_id,
        "preset": preset,
        "filename": target.name,
        "path": _workspace_rel(target),
        "bytes": target.stat().st_size,
        "created_at": _now(),
        "source": str(render_path),
        "width": width or render.get("width"),
        "height": height or render.get("height"),
    }
    _atomic_json(directory / f"{target.stem}.json", record)
    project = load_project(project_id)
    if project is not None:
        project["status"] = "delivered"
        save_project(project)
    return record


# --------------------------------------------------------------------------- #
# soft delete (undo in the project page)
# --------------------------------------------------------------------------- #
_TRASH_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


def _trash_dir() -> Path:
    return PROJECTS / ".trash"


def trash_project(project_id: str) -> str:
    """Move a project into projects/.trash/<token>/ and return the token."""
    source = _project_dir(project_id)
    if not source.is_dir():
        raise FileNotFoundError(project_id)
    token = uuid.uuid4().hex
    target = _trash_dir() / token
    target.mkdir(parents=True, exist_ok=True)
    os.replace(source, target / "project")
    _atomic_json(target / "meta.json", {
        "token": token,
        "project_id": project_id,
        "at": _now(),
    })
    return token


def restore_project(token: str) -> dict[str, Any]:
    if not _TRASH_TOKEN_RE.match(token or ""):
        raise ValueError("invalid trash token")
    target = _trash_dir() / token
    meta = _read_json(target / "meta.json")
    if meta is None:
        raise FileNotFoundError(token)
    project_id = _check_id(str(meta.get("project_id") or ""), "project_id")
    destination = PROJECTS / project_id
    if destination.exists():
        raise FileExistsError(project_id)
    os.replace(target / "project", destination)
    shutil.rmtree(target, ignore_errors=True)
    project = load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    return project


def persona_snapshot(persona_id: str | None) -> dict[str, Any] | None:
    """Project-facing view of a reusable persona; avoids a hard import cycle."""
    if not persona_id:
        return None
    from adplus import personas
    return personas.persona_snapshot(persona_id)


def product_snapshot(product_id: str | None) -> dict[str, Any] | None:
    if not product_id:
        return None
    from adplus import products
    return products.product_snapshot(product_id)
