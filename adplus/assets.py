"""Asset inventory for the 资产 module.

Assets come from three places and are addressed by a stable hash of their
workspace-relative path:

    uploads/<day>/<file>              source = upload
    projects/<id>/assets/<file>       source = project
    projects/<id>/renders/<file>      source = render

The UI never needs an absolute path; every record carries a repo-relative
``path`` that /api/media and /api/thumb can serve.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from adplus import project_store
from adplus.paths import PROJECTS, UPLOADS

IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".heic"}
VIDEO = {".mp4", ".mov", ".webm", ".m4v"}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def kind_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE:
        return "image"
    if suffix in VIDEO:
        return "video"
    if suffix in AUDIO:
        return "audio"
    return "file"


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name or "asset").strip("-")
    return (cleaned or "asset")[:100]


def _workspace_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECTS.parent.resolve()))
    except (ValueError, OSError):
        return str(path)


def asset_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def _record(path: Path, source: str, project_id: str | None) -> dict[str, Any] | None:
    if not path.is_file() or path.name.startswith("."):
        return None
    kind = kind_of(path)
    if kind == "file":
        return None
    rel = _workspace_rel(path)
    stat = path.stat()
    return {
        "id": asset_id(rel),
        "name": path.name,
        "path": rel,
        "kind": kind,
        "source": source,
        "project_id": project_id,
        "bytes": stat.st_size,
        "mtime": stat.st_mtime,
    }


def list_assets(
    project_id: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    query: str = "",
    limit: int = 300,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if UPLOADS.is_dir() and source in (None, "upload"):
        for path in UPLOADS.rglob("*"):
            record = _record(path, "upload", None)
            if record:
                rows.append(record)
    if PROJECTS.is_dir():
        for project in PROJECTS.iterdir():
            if not project.is_dir() or project.name.startswith("."):
                continue
            if project_id and project.name != project_id:
                continue
            for folder, src in (("assets", "project"), ("renders", "render")):
                directory = project / folder
                if not directory.is_dir() or source not in (None, src):
                    continue
                for path in directory.rglob("*"):
                    record = _record(path, src, project.name)
                    if record:
                        rows.append(record)
    q = query.strip().lower()
    if kind and kind != "all":
        rows = [row for row in rows if row["kind"] == kind]
    if q:
        rows = [row for row in rows if q in row["name"].lower() or q in row["path"].lower()]
    rows.sort(key=lambda row: row["mtime"], reverse=True)
    return rows[: max(1, limit)]


def get_asset(asset: str) -> dict[str, Any] | None:
    for row in list_assets(limit=10_000):
        if row["id"] == asset:
            return row
    return None


def probe(record: dict[str, Any]) -> dict[str, Any]:
    path = PROJECTS.parent / record["path"]
    out = dict(record)
    if record["kind"] == "image":
        try:
            from PIL import Image

            with Image.open(path) as image:
                out["width"], out["height"] = image.size
        except Exception:
            pass
    elif record["kind"] in ("video", "audio"):
        try:
            ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
            proc = subprocess.run(
                [
                    ffprobe, "-v", "error", "-show_entries",
                    "stream=width,height,codec_type:format=duration",
                    "-of", "json", str(path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            data = json.loads(proc.stdout or "{}")
            for stream in data.get("streams") or []:
                if stream.get("width"):
                    out["width"] = stream["width"]
                if stream.get("height"):
                    out["height"] = stream["height"]
                if stream.get("codec_type"):
                    out.setdefault("codec", stream["codec_type"])
            duration = (data.get("format") or {}).get("duration")
            if duration:
                out["duration_s"] = round(float(duration), 3)
        except Exception:
            pass
    return out


def _unique_path(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(name)
    stem, dot, suffix = safe.rpartition(".")
    if not dot:
        stem, suffix = safe, ""
    target = directory / (f"{stem}.{suffix}" if suffix else stem)
    counter = 2
    while target.exists():
        target = directory / (f"{stem}-{counter}.{suffix}" if suffix else f"{stem}-{counter}")
        counter += 1
    return target


def reuse_asset(
    asset: str,
    project_id: str,
    shot_id: str | None = None,
    mode: str = "reference",
) -> dict[str, Any]:
    record = get_asset(asset)
    if record is None:
        raise FileNotFoundError(asset)
    source = (PROJECTS.parent / record["path"]).resolve()
    if not source.is_file():
        raise FileNotFoundError(record["path"])
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    target = _unique_path(PROJECTS / project_id / "assets", source.name)
    shutil.copy2(source, target)
    target_rel = _workspace_rel(target)

    version = None
    shot = None
    if shot_id:
        current = project_store.ensure_version(project_id)
        if current is None:
            raise ValueError("project has no version")
        shot = project_store.update_shot(
            project_id,
            str(current["id"]),
            shot_id,
            {"preview": target_rel, "status": "ready"},
        )
        version = project_store.load_version(project_id, str(current["id"]))
    else:
        refs = list((project.get("brief") or {}).get("reference_assets") or [])
        if target_rel not in refs:
            refs.append(target_rel)
        project["brief"] = {**(project.get("brief") or {}), "reference_assets": refs}
        project_store.save_project(project)

    return {
        "asset": _record(target, "project", project_id),
        "project": project_store.load_project(project_id),
        "shot": shot,
        "version": version,
    }


def delete_asset(asset: str) -> bool:
    record = get_asset(asset)
    if record is None:
        return False
    if record["source"] not in ("upload", "project"):
        raise ValueError("renders cannot be deleted from assets")
    path = (PROJECTS.parent / record["path"]).resolve()
    root = (UPLOADS if record["source"] == "upload" else PROJECTS).resolve()
    if root not in path.parents:
        raise ValueError("path outside asset roots")
    if not path.is_file():
        return False
    path.unlink()
    return True


def upload_asset(raw: bytes, name: str) -> dict[str, Any]:
    if not raw:
        raise ValueError("empty upload")
    day = time.strftime("%Y%m%d")
    directory = UPLOADS / day
    directory.mkdir(parents=True, exist_ok=True)
    base = _safe_name(name or "upload")
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    digest = hashlib.sha1(raw[:1_000_000]).hexdigest()[:8]
    target = directory / (f"{stem}-{digest}" + (f".{suffix}" if suffix else ""))
    if kind_of(target) == "file":
        raise ValueError("unsupported file type")  # reject before writing junk to uploads/
    target.write_bytes(raw)
    record = _record(target, "upload", None)
    if record is None:
        raise ValueError("unsupported file type")
    return record


def attach_file(raw: bytes, name: str) -> dict[str, Any]:
    """Chat attachment of any type: kept outside the asset library.

    Scripts, notes, subtitle files and PDFs are not media, but the agent can
    still read them from the workspace path we hand back.
    """
    if not raw:
        raise ValueError("empty attachment")
    directory = UPLOADS / "attachments" / time.strftime("%Y%m%d")
    directory.mkdir(parents=True, exist_ok=True)
    base = _safe_name(name or "attachment")
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    digest = hashlib.sha1(raw[:1_000_000]).hexdigest()[:8]
    target = directory / (f"{stem}-{digest}" + (f".{suffix}" if suffix else ""))
    target.write_bytes(raw)
    rel = _workspace_rel(target)
    return {
        "id": asset_id(rel),
        "name": target.name,
        "path": rel,
        "bytes": len(raw),
    }
