"""Restyle project store.

A restyle is a normal Ad+ project with ``format_id=reference_restyle`` plus a
``restyle/`` sidecar.  Reusing projects gives us jobs, media serving, trash and
persona/product references without a second storage system.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from adplus import jobs, project_store
from adplus.paths import PROJECTS, UPLOADS, WORKSPACE
from adplus.restyle import analysis, plans

FORMAT_ID = "reference_restyle"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _root(project_id: str) -> Path:
    return PROJECTS / project_id / "restyle"


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hash(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_from_project(project_id: str) -> dict[str, Any] | None:
    return _read(_root(project_id) / "source.json")


def _blueprint(project_id: str) -> dict[str, Any] | None:
    return _read(_root(project_id) / "blueprint.json")


def _plan(project_id: str) -> dict[str, Any] | None:
    return _read(_root(project_id) / "plan.json")


def is_restyle(project: dict[str, Any] | None) -> bool:
    return bool(project and project.get("format_id") == FORMAT_ID)


def _resolve_source(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = WORKSPACE / path
    path = path.resolve()
    roots = [UPLOADS.resolve(), PROJECTS.resolve()]
    if not any(root == path or root in path.parents for root in roots):
        raise ValueError("source video must be under uploads/ or projects/")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValueError(f"unsupported video type: {path.suffix}")
    return path


def create(path: str, title: str | None = None, rights_confirmed: bool = False) -> dict[str, Any]:
    source_path = _resolve_source(path)
    meta = analysis.probe(source_path)
    if not rights_confirmed:
        raise ValueError("rights_confirmed_required")
    project_title = (title or source_path.stem or "改写").strip()[:80]
    project = project_store.create_project(
        project_title,
        format_id=FORMAT_ID,
        pipeline_type="hybrid",
        aspect=meta.get("aspect") or "9:16",
        duration_s=max(0.5, float(meta.get("duration_s") or 0)),
        platform="douyin",
        route={"id": "hybrid", "pipeline": "hybrid", "runtime": "restyle"},
    )
    project_id = str(project["project_id"])
    root = _root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "thumbs").mkdir(exist_ok=True)
    stored = root / f"source{source_path.suffix.lower()}"
    shutil.copy2(source_path, stored)
    source = {
        "path": _rel(stored),
        "original_path": _rel(source_path),
        "hash": _hash(stored),
        "probe": meta,
        "rights": {
            "confirmed": True,
            "note": "",
            "confirmed_at": _now(),
        },
        "created_at": _now(),
    }
    _write(root / "source.json", source)
    _write(root / "plan.json", plans.default_plan())
    return detail(project_id) or {}


def list_restyles() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not PROJECTS.is_dir():
        return rows
    for child in PROJECTS.iterdir():
        if not child.is_dir():
            continue
        project = project_store.load_project(child.name)
        if not is_restyle(project):
            continue
        assert project is not None
        source = _source_from_project(child.name) or {}
        blueprint = _blueprint(child.name) or {}
        shots = blueprint.get("shots") or []
        rows.append({
            "id": child.name,
            "title": project.get("title") or child.name,
            "status": project.get("status") or "draft",
            "aspect": project.get("aspect"),
            "duration_s": project.get("duration_s"),
            "cover": project.get("cover") or (shots[0].get("keyframe") if shots else None),
            "shot_count": len(shots),
            "caption_count": blueprint.get("caption_count") or 0,
            "analyzed": bool(blueprint),
            "updated_at": project.get("updated_at"),
            "source_path": source.get("path"),
        })
    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return rows


def detail(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    if project is None or not is_restyle(project):
        return None
    return {
        "project": project,
        "source": _source_from_project(project_id),
        "blueprint": _blueprint(project_id),
        "plan": _plan(project_id),
        "jobs": jobs.list_jobs(project_id, limit=8),
    }


def save_plan(project_id: str, patch: dict[str, Any], revision: int | None = None) -> dict[str, Any]:
    if project_store.load_project(project_id) is None:
        raise FileNotFoundError(project_id)
    current = _plan(project_id) or plans.default_plan(_blueprint(project_id))
    updated = plans.apply_patch(current, patch, revision)
    _write(_root(project_id) / "plan.json", updated)
    try:
        project_store.update_project(project_id, {"status": "producing"})
    except ValueError:
        pass
    return updated


def start_analysis(project_id: str) -> dict[str, Any]:
    if project_store.load_project(project_id) is None:
        raise FileNotFoundError(project_id)
    job = jobs.start("restyle_analyze", project_id, frames_total=1)
    job_id = str(job["id"])

    def run() -> None:
        try:
            def progress(value: float) -> None:
                jobs.update(job, progress=max(0.0, min(1.0, float(value))),
                            frames_done=1 if value >= 1 else 0)

            analysis.analyze_project(project_id, progress=progress)
            jobs.finish(job, "done", output="restyle/blueprint.json")
        except Exception as exc:  # report, do not crash the worker
            jobs.finish(job, "failed", error=str(exc)[:500])

    thread = threading.Thread(target=run, name=f"restyle-analyze-{job_id}", daemon=True)
    thread.start()
    return job


def delete(project_id: str) -> str:
    if project_store.load_project(project_id) is None:
        raise FileNotFoundError(project_id)
    return project_store.trash_project(project_id)
