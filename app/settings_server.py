"""Settings server for the OpenMontage desktop app.

Serves the key/capability UI and the JSON API the shell (and, later, the
Tauri window) talks to. Runs on localhost only.

    python -m app.settings_server --port 8765
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import asyncio
import re
import threading
import time
from collections import deque

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

import adplus
from adplus import assets as asset_store
from adplus import project_store
from adplus import personas as persona_store
from adplus import persona_generator
from adplus import products as product_store
from adplus import digital_human
from adplus import product_composite
from adplus import canonical_artifacts
from adplus import request_probe
from adplus import pipeline_runner
from adplus import local_tools
from adplus import oms_tools
from adplus import formats
from adplus import capabilities as model_caps
from adplus.restyle import segment as restyle_segment
from adplus.restyle import store as restyle_store
from app import capabilities, config_store, env_utils, pi_bridge, secrets_store

UI_DIR = Path(__file__).resolve().parent / "ui"

app = FastAPI(title="OpenMontage Settings", version="0.1.0")


@app.on_event("startup")
def _warm_registry() -> None:
    """Discover tools in the background so the first settings open is fast.

    Registry discovery imports ~200 tool modules and takes several seconds;
    doing it at startup keeps /api/state responsive for the first click.
    """
    def warm() -> None:
        try:
            oms_tools.register()
            local_tools.ensure_local_tools()
            capabilities.apply_secrets_to_env()
            capabilities.matrix()
        except Exception:
            pass

    threading.Thread(target=warm, name="registry-warmup", daemon=True).start()


class KeyPayload(BaseModel):
    name: str
    value: str


try:  # the Keychain is the source of truth; children read the mirror
    secrets_store.export_mirror_for_children()
except Exception:  # never block startup on secret plumbing
    pass

try:  # where finished videos land (OPENMONTAGE_PROJECTS_DIR)
    config_store.apply_to_env()
except Exception:
    pass

try:  # jobs whose process died with a previous app instance
    from adplus import jobs as _job_store

    _INTERRUPTED = _job_store.recover_interrupted()
except Exception:
    _INTERRUPTED = 0


def _pi(*args: str) -> dict[str, Any]:
    exe = env_utils.find_node_tool("pi")
    if not exe or not Path(exe).exists():
        return {"available": False, "error": "pi not found (install Pi or add ~/.local/bin to PATH)"}
    env = env_utils.spawn_env(secrets_store.merged_env())
    try:
        proc = subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=60, env=env
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": str(exc)}
    return {
        "available": True,
        "code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"


@app.get("/icon.svg")
def icon() -> FileResponse:
    if not ICON_PATH.is_file():
        raise HTTPException(status_code=404, detail="icon missing")
    return FileResponse(ICON_PATH, media_type="image/svg+xml")


@app.get("/splash")
def splash_page() -> FileResponse:
    return FileResponse(UI_DIR / "splash.html")


UI_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _spa_index() -> FileResponse | None:
    index = UI_DIST / "index.html"
    return FileResponse(index) if index.is_file() else None


def _require_spa() -> FileResponse:
    """The Solid build is the only UI; a missing dist is a build error, not a fallback."""
    spa = _spa_index()
    if spa is None:
        raise HTTPException(
            status_code=503,
            detail="UI build missing — run: cd frontend && pnpm install && pnpm build",
        )
    return spa


def ui_mode(request: Request) -> str:
    """Kept for compatibility: the legacy pages are gone, `?ui=` is a no-op."""
    return os.environ.get("ADPLUS_UI", "next")


@app.get("/onboarding")
def onboarding_page() -> Any:
    return _require_spa()


@app.get("/settings")
def settings_page() -> Any:
    return _require_spa()


@app.get("/")
def index() -> Any:
    """Workspace, gated: no usable model means no onboarding."""
    if not bootstrap()["has_model"]:
        return RedirectResponse("/onboarding", status_code=307)
    return _require_spa()


@app.get("/projects")
@app.get("/projects/{rest:path}")
def spa_projects(rest: str = "") -> Any:
    return _require_spa()


@app.get("/studio")
@app.get("/studio/{rest:path}")
def spa_studio(rest: str = "") -> Any:
    return _require_spa()


@app.get("/tasks")
def spa_tasks() -> Any:
    return _require_spa()


@app.get("/assets")
def spa_assets_root() -> Any:
    return _require_spa()


@app.get("/chat/{rest:path}")
def spa_chat(rest: str) -> Any:
    """Deep links into the SPA (session id lives in the URL)."""
    return _require_spa()


@app.get("/assets/{rest:path}")
def spa_assets(request: Request, rest: str) -> Any:
    target = UI_DIST / "assets" / rest
    if target.is_file():
        return FileResponse(target)
    # /assets/brands and /assets/templates are client tabs, not static files.
    if "." not in Path(rest).name:
        return _require_spa()
    raise HTTPException(status_code=404, detail="asset not found")


_MODEL_CACHE: dict[str, Any] = {"at": 0.0, "models": []}


def list_models(force: bool = False) -> list[dict[str, str]]:
    """Available Pi models, cached for 30s (the CLI call costs ~1s)."""
    import time as _time

    if not force and _time.time() - _MODEL_CACHE["at"] < 30:
        return _MODEL_CACHE["models"]
    out = _pi("--list-models")
    rows: list[dict[str, str]] = []
    for line in (out.get("stdout") or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in {"provider", "No"}:
            rows.append({"provider": parts[0], "model": parts[1], "kind": "text"})
    _MODEL_CACHE.update(at=_time.time(), models=rows)
    return rows


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    models = list_models()
    return {
        "ready": True,
        "has_model": bool(models),
        "models": models,
        "first_run": not (secrets_store.app_data_dir() / "first-run-done").exists(),
        "version": app.version,
        "app_data": str(secrets_store.app_data_dir()),
        "workspace": str(adplus.paths.WORKSPACE),
        "projects": str(adplus.paths.PROJECTS),
    }


@app.get("/api/state")
def state() -> dict[str, Any]:
    return capabilities.snapshot()


@app.post("/api/keys")
def save_key(payload: KeyPayload) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        result = secrets_store.set_secret(payload.name.strip(), payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    capabilities.apply_secrets_to_env()
    return {"saved": result, "state": capabilities.snapshot()}


@app.delete("/api/keys/{name}")
def delete_key(name: str) -> dict[str, Any]:
    result = secrets_store.delete_secret(name)
    capabilities.apply_secrets_to_env()
    return {"removed": result, "state": capabilities.snapshot()}


@app.post("/api/recheck")
def recheck() -> dict[str, Any]:
    applied = capabilities.apply_secrets_to_env()
    return {"applied": applied, "state": capabilities.snapshot()}


@app.get("/api/pi/status")
def pi_status() -> dict[str, Any]:
    return {
        "version": _pi("--version"),
        "models": _pi("--list-models"),
        "mcp": _pi("mcp", "list", "--json"),
    }


THUMB_DIR = secrets_store.app_data_dir() / "thumbs"


UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def _safe_name(name: str) -> str:
    keep = [c for c in name if c.isalnum() or c in " ._-()[]" or ord(c) > 127]
    cleaned = "".join(keep).strip() or "file"
    return cleaned[:120]


@app.post("/api/upload")
async def upload(request: Request, name: str = "") -> dict[str, Any]:
    """Raw bytes upload (no multipart dependency); UI sends the File body."""
    raw = await request.body()
    if len(raw) > 2 * 1024**3:
        raise HTTPException(status_code=413, detail="file too large (2 GB max)")
    try:
        record = asset_store.upload_asset(raw, name or "upload")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **record, "asset": record}


@app.get("/api/uploads")
def list_uploads(limit: int = 40) -> dict[str, Any]:
    rows = asset_store.list_assets(source="upload", limit=limit)
    return {"files": rows, "assets": rows}


@app.get("/api/thumb")
def thumb(path: str, width: int = 360) -> FileResponse:
    """First-frame poster for a render, generated once and cached on disk."""
    import hashlib

    src = (Path(__file__).resolve().parent.parent / path).resolve()
    roots = [adplus.paths.PROJECTS.resolve(), adplus.paths.UPLOADS.resolve()]
    if not any(root == src or root in src.parents for root in roots) or not src.is_file():
        raise HTTPException(status_code=404, detail="no such media")
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{src}:{src.stat().st_mtime}:{width}".encode()).hexdigest()[:16]
    out = THUMB_DIR / f"{key}.jpg"
    if not out.is_file():
        ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        for seek in ("1", "0"):
            proc = subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-ss", seek, "-i", str(src),
                 "-vf", f"scale={max(80, min(720, width))}:-1", "-frames:v", "1", "-q:v", "4", str(out)],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                break
        if not out.is_file():
            raise HTTPException(status_code=415, detail="thumbnail extraction failed")
    return FileResponse(out, media_type="image/jpeg")


MEDIA_ROOTS = {"projects": adplus.paths.PROJECTS, "uploads": adplus.paths.UPLOADS}


@app.get("/api/media")
def media(path: str) -> FileResponse:
    """Serve a produced file (video/image) by path, restricted to projects/."""
    target = (Path(__file__).resolve().parent.parent / path).resolve()
    roots = [root.resolve() for root in MEDIA_ROOTS.values()]
    if not any(root == target or root in target.parents for root in roots):
        raise HTTPException(status_code=403, detail="path outside media roots")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    return FileResponse(target)


class IntegrationPayload(BaseModel):
    exposure: str


@app.get("/api/pi/integration")
def pi_integration() -> dict[str, Any]:
    config_path = Path.home() / ".pi" / "agent" / "mcp.json"
    servers: list[dict[str, Any]] = []
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        for name, entry in (data.get("mcpServers") or {}).items():
            servers.append(
                {
                    "name": name,
                    "exposure": entry.get("exposure", "codemode"),
                    "timeout": entry.get("timeout", 60),
                    "cwd": entry.get("cwd"),
                }
            )
    return {
        "config": str(config_path),
        "servers": servers,
        "trust": {
            "approve_flag": True,
            "note": "app 启动 Pi 时总是带 --approve，因此项目级 .pi/ 与 .agents/skills 均被信任",
        },
    }


@app.post("/api/pi/integration")
def set_pi_integration(payload: IntegrationPayload) -> dict[str, Any]:
    allowed = {"direct", "codemode", "deferred", "hidden"}
    if payload.exposure not in allowed:
        raise HTTPException(status_code=400, detail=f"exposure must be one of {sorted(allowed)}")
    config_path = Path.home() / ".pi" / "agent" / "mcp.json"
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail="mcp.json missing; launch the app once to create it")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    entry = (data.get("mcpServers") or {}).get("openmontage")
    if not entry:
        raise HTTPException(status_code=404, detail="openmontage server not configured")
    entry["exposure"] = payload.exposure
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"exposure": payload.exposure, "config": str(config_path)}


class ProjectCreatePayload(BaseModel):
    project_id: str | None = None
    title: str
    brief: dict[str, Any] | None = None
    platform: str = "douyin"
    aspect: str = "9:16"
    duration_s: float = 15
    quality_tier: str = "standard"
    pipeline_type: str = "cinematic"
    persona_id: str | None = None
    product_id: str | None = None
    format_id: str | None = None
    route: dict[str, Any] | None = None


class ProjectPatchPayload(BaseModel):
    title: str | None = None
    status: str | None = None
    platform: str | None = None
    aspect: str | None = None
    duration_s: float | None = None
    quality_tier: str | None = None
    brand_id: str | None = None
    persona_id: str | None = None
    product_id: str | None = None
    format_id: str | None = None
    brief: dict[str, Any] | None = None
    current_version_id: str | None = None
    pipeline_type: str | None = None
    cover: str | None = None


class VersionCreatePayload(BaseModel):
    label: str | None = None
    parent_id: str | None = None
    copy_shots: bool = True


class VersionPatchPayload(BaseModel):
    current: bool | None = None
    status: str | None = None
    label: str | None = None
    render: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    cost_usd: float | None = None


class ReorderPayload(BaseModel):
    order: list[str]


class ShotCreatePayload(BaseModel):
    after_id: str | None = None
    role: str = "build"
    description: str = ""
    duration_s: float = 2.5
    framing: str = ""
    movement: str = ""
    transition_in: str = ""
    transition_out: str = ""
    on_screen_text: str = ""
    narration: str = ""
    status: str = "planned"
    preview: str | None = None
    production_method: str | None = None
    shot_language: dict[str, Any] | None = None
    asset_refs: dict[str, Any] | None = None
    generation_spec: dict[str, Any] | None = None
    timeline: dict[str, Any] | None = None
    persona_id: str | None = None
    product_id: str | None = None


class ShotPatchPayload(BaseModel):
    role: str | None = None
    description: str | None = None
    framing: str | None = None
    movement: str | None = None
    transition_in: str | None = None
    transition_out: str | None = None
    on_screen_text: str | None = None
    narration: str | None = None
    status: str | None = None
    locked: bool | None = None
    preview: str | None = None
    duration_s: float | None = None
    take_count: int | None = None
    cost_usd: float | None = None
    production_method: str | None = None
    shot_language: dict[str, Any] | None = None
    asset_refs: dict[str, Any] | None = None
    generation_spec: dict[str, Any] | None = None
    timeline: dict[str, Any] | None = None
    persona_id: str | None = None
    product_id: str | None = None


class PersonaPayload(BaseModel):
    name: str | None = None
    kind: str | None = None
    status: str | None = None
    source_path: str | None = None
    preview_path: str | None = None
    asset_paths: list[str] | None = None
    description: str | None = None
    gender: str | None = None
    age_range: str | None = None
    look: str | None = None
    wardrobe: str | None = None
    scene: str | None = None
    tags: list[str] | None = None
    voice: dict[str, Any] | None = None
    rights: dict[str, Any] | None = None
    providers: dict[str, Any] | None = None


class PersonaGeneratePayload(BaseModel):
    prompt: str = ""
    count: int = 4
    aspect_ratio: str = "3:4"
    reference_path: str | None = None
    model: str = "image-01"


class DigitalHumanPayload(BaseModel):
    shot_id: str
    version_id: str | None = None
    profile_id: str = "kling-avatar"
    persona_id: str | None = None
    product_id: str | None = None
    audio_path: str | None = None
    video_path: str | None = None
    prompt: str | None = None


class PipelineBootstrapPayload(BaseModel):
    version_id: str | None = None
    approve: bool = True


class PipelineCompletePayload(BaseModel):
    version_id: str
    render_path: str
    product_id: str | None = None
    approve: bool = True


class PipelineAssetsPayload(BaseModel):
    shot_id: str
    version_id: str | None = None
    profile_id: str = "kling-avatar"
    persona_id: str | None = None
    product_id: str | None = None
    audio_path: str | None = None
    execute: bool = False


class RequestProbePayload(BaseModel):
    profile_id: str
    inputs: dict[str, Any]


class CanonicalSyncPayload(BaseModel):
    version_id: str | None = None


class ProductCompositePayload(BaseModel):
    shot_id: str
    version_id: str | None = None
    product_id: str | None = None
    base_video_path: str | None = None
    start_s: float = 2.0
    end_s: float = 8.0
    position: str = "bottom_left"


class ProductPayload(BaseModel):
    name: str | None = None
    sku: str | None = None
    brand: str | None = None
    label_text: str | None = None
    category: str | None = None
    hero_path: str | None = None
    detail_paths: list[str] | None = None
    tags: list[str] | None = None
    status: str | None = None
    locked: bool | None = None
    rights: dict[str, Any] | None = None


class BrandPayload(BaseModel):
    name: str | None = None
    logo: str | None = None
    colors: list[str] | None = None
    font_cn: str | None = None
    font_en: str | None = None
    tone: list[str] | None = None
    voice: dict[str, Any] | None = None
    banned_words: list[str] | None = None
    default: bool | None = None


class ApplyBrandPayload(BaseModel):
    project_id: str


class ReviewDecisionPayload(BaseModel):
    shot_id: str
    status: str = "pass"
    note: str = ""


class ReviewPayload(BaseModel):
    version_id: str
    approved: bool
    decisions: list[ReviewDecisionPayload] | None = None
    comment: str = ""


class ExportPayload(BaseModel):
    version_id: str
    preset: str = "original"
    filename: str | None = None


def _detail_or_404(project_id: str) -> dict[str, Any]:
    detail = project_store.project_detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="project not found")
    return detail


@app.get("/api/projects")
def projects(include_restyle: bool = False) -> dict[str, Any]:
    rows = project_store.list_projects()
    if not include_restyle:
        rows = [row for row in rows if row.get("format_id") != "reference_restyle"]
    return {"projects": rows}


@app.post("/api/projects")
def create_project(payload: ProjectCreatePayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    title = str(fields.pop("title"))
    project_id = fields.pop("project_id", None)
    try:
        project = project_store.create_project(title, project_id, **fields)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"project already exists: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project": project}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    try:
        token = project_store.trash_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return {"trash_id": token}


@app.post("/api/projects/restore/{token}")
def restore_project(token: str) -> dict[str, Any]:
    try:
        project = project_store.restore_project(token)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trash entry not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="project already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"project": project}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return _detail_or_404(project_id)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatchPayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    try:
        project_store.update_project(project_id, fields)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail_or_404(project_id)


@app.get("/api/projects/{project_id}/versions")
def get_versions(project_id: str) -> dict[str, Any]:
    if project_store.load_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {"versions": project_store.list_versions(project_id)}


@app.post("/api/projects/{project_id}/versions")
def post_version(project_id: str, payload: VersionCreatePayload) -> dict[str, Any]:
    try:
        version = project_store.create_version(
            project_id, label=payload.label, parent_id=payload.parent_id, copy_shots=payload.copy_shots
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"version": version, "project": project_store.load_project(project_id)}


@app.patch("/api/projects/{project_id}/versions/{version_id}")
def patch_version(project_id: str, version_id: str, payload: VersionPatchPayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    current = fields.pop("current", None)
    try:
        if fields:
            project_store.update_version(project_id, version_id, fields)
        if current is not None:
            project_store.set_current_version(project_id, version_id) if current else None
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "version": project_store.load_version(project_id, version_id),
        "project": project_store.load_project(project_id),
    }


@app.patch("/api/projects/{project_id}/versions/{version_id}/shots/reorder")
def reorder_shots(project_id: str, version_id: str, payload: ReorderPayload) -> dict[str, Any]:
    try:
        version = project_store.reorder_shots(project_id, version_id, payload.order)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"version": version}


@app.post("/api/projects/{project_id}/versions/{version_id}/shots")
def create_shot(project_id: str, version_id: str, payload: ShotCreatePayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    after_id = fields.pop("after_id", None)
    try:
        version = project_store.add_shot(project_id, version_id, after_id=after_id, **fields)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"version": version}


@app.patch("/api/projects/{project_id}/versions/{version_id}/shots/{shot_id}")
def patch_shot(project_id: str, version_id: str, shot_id: str, payload: ShotPatchPayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    try:
        shot = project_store.update_shot(project_id, version_id, shot_id, fields)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="shot not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"shot": shot, "version": project_store.load_version(project_id, version_id)}


@app.delete("/api/projects/{project_id}/versions/{version_id}/shots/{shot_id}")
def remove_shot(project_id: str, version_id: str, shot_id: str) -> dict[str, Any]:
    try:
        version = project_store.delete_shot(project_id, version_id, shot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="shot not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"version": version}


def _project_or_404(project_id: str) -> dict[str, Any]:
    project = project_store.load_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@app.get("/api/projects/{project_id}/plan")
def get_plan(project_id: str) -> dict[str, Any]:
    payload = project_store.plan_payload(project_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="project not found")
    from adplus import proposals as proposal_store

    payload["proposal_view"] = proposal_store.proposal_payload(project_id)
    return payload


@app.get("/api/projects/{project_id}/production")
def get_production(project_id: str) -> dict[str, Any]:
    from adplus import production

    payload = production.production_payload(project_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="project not found")
    return payload


@app.post("/api/projects/{project_id}/route")
def set_route(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from adplus import production

    _project_or_404(project_id)
    try:
        production.save_route(project_id, str(payload.get("route_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return production.production_payload(project_id) or {}


@app.post("/api/projects/{project_id}/script")
def save_script(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from adplus import production

    _project_or_404(project_id)
    lines = payload.get("lines")
    if not isinstance(lines, list):
        raise HTTPException(status_code=400, detail="lines required")
    return {"script": production.save_script(project_id, lines)}


@app.post("/api/projects/{project_id}/stages/{stage}/approve")
def approve_stage(project_id: str, stage: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from adplus import production

    _project_or_404(project_id)
    try:
        result = production.approve(project_id, stage, str((payload or {}).get("comment") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/api/projects/{project_id}/compose")
def start_compose(project_id: str) -> dict[str, Any]:
    from adplus import production
    from adplus import local_motion

    payload = production.production_payload(project_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="project not found")
    if payload["route"]["id"] != "local_motion":
        raise HTTPException(status_code=400, detail="该路线暂未接入自动渲染")
    try:
        result = local_motion.start(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/api/projects/{project_id}/proposal")
def get_proposal(project_id: str) -> dict[str, Any]:
    from adplus import proposals as proposal_store
    from app import proposal_runner

    _project_or_404(project_id)
    proposal = proposal_store.proposal_payload(project_id)
    return {"proposal": proposal, "job": proposal_runner.status(project_id)}


@app.post("/api/projects/{project_id}/proposal")
def start_proposal(project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from adplus import proposals as proposal_store
    from app import proposal_runner

    _project_or_404(project_id)
    body = payload or {}
    brief = body.get("brief")
    if brief is not None and not isinstance(brief, dict):
        raise HTTPException(status_code=400, detail="brief must be an object")
    try:
        job = proposal_runner.start(project_id, brief=brief, feedback=str(body.get("feedback") or ""))
    except proposal_runner.AlreadyRunning as exc:
        raise HTTPException(status_code=409, detail="proposal generation already running") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return {"job": job, "proposal": proposal_store.proposal_payload(project_id)}


@app.post("/api/projects/{project_id}/proposal/cancel")
def cancel_proposal(project_id: str) -> dict[str, Any]:
    from app import proposal_runner

    _project_or_404(project_id)
    return {"job": proposal_runner.cancel(project_id)}


@app.get("/api/projects/{project_id}/review")
def get_review(project_id: str, version_id: str = "") -> dict[str, Any]:
    _project_or_404(project_id)
    payload = project_store.review_payload(project_id, version_id or None)
    if payload is None:
        raise HTTPException(status_code=404, detail="version not found")
    return payload


@app.post("/api/projects/{project_id}/review")
def post_review(project_id: str, payload: ReviewPayload) -> dict[str, Any]:
    _project_or_404(project_id)
    current = project_store.review_payload(project_id, payload.version_id)
    qa_status = str((current or {}).get("qa", {}).get("status") or "unknown")
    decisions = [item.model_dump() for item in (payload.decisions or [])]
    try:
        record = project_store.save_review(
            project_id,
            payload.version_id,
            payload.approved,
            decisions=decisions,
            comment=payload.comment,
            qa_status=qa_status,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "review": record,
        "detail": project_store.project_detail(project_id),
    }


@app.get("/api/projects/{project_id}/deliverables")
def get_deliverables(project_id: str) -> dict[str, Any]:
    _project_or_404(project_id)
    return {"deliverables": project_store.list_deliverables(project_id)}


@app.post("/api/projects/{project_id}/export")
def post_export(project_id: str, payload: ExportPayload) -> dict[str, Any]:
    _project_or_404(project_id)
    try:
        record = project_store.export_version(
            project_id,
            payload.version_id,
            preset=payload.preset,
            filename=payload.filename,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "deliverable": record,
        "deliverables": project_store.list_deliverables(project_id),
        "detail": project_store.project_detail(project_id),
    }


class ReuseAssetPayload(BaseModel):
    project_id: str
    shot_id: str | None = None
    mode: str = "reference"


@app.get("/api/assets")
def list_assets(
    project_id: str = "",
    kind: str = "",
    source: str = "",
    q: str = "",
    limit: int = 300,
) -> dict[str, Any]:
    return {
        "assets": asset_store.list_assets(
            project_id=project_id or None,
            kind=kind or None,
            source=source or None,
            query=q,
            limit=min(max(limit, 1), 1000),
        )
    }


@app.get("/api/assets/{asset_id}")
def get_asset(asset_id: str) -> dict[str, Any]:
    record = asset_store.get_asset(asset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"asset": asset_store.probe(record)}


@app.post("/api/assets/{asset_id}/reuse")
def reuse_asset(asset_id: str, payload: ReuseAssetPayload) -> dict[str, Any]:
    if payload.mode not in ("reference", "replace"):
        raise HTTPException(status_code=400, detail="mode must be reference or replace")
    try:
        result = asset_store.reuse_asset(
            asset_id,
            payload.project_id,
            shot_id=payload.shot_id if payload.mode == "replace" else None,
            mode=payload.mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, Any]:
    try:
        removed = asset_store.delete_asset(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"removed": True}


@app.get("/api/personas")
def list_personas(include_archived: bool = False) -> dict[str, Any]:
    return {"personas": persona_store.list_personas(include_archived=include_archived)}


@app.post("/api/personas")
def create_persona(payload: PersonaPayload) -> dict[str, Any]:
    try:
        persona = persona_store.save_persona(payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"persona": persona}


@app.post("/api/personas/generate")
def generate_persona_candidates(payload: PersonaGeneratePayload) -> dict[str, Any]:
    reference = payload.reference_path
    if reference:
        target = (Path(__file__).resolve().parent.parent / reference).resolve()
        uploads = adplus.paths.UPLOADS.resolve()
        if not (target == uploads or uploads in target.parents) or not target.is_file():
            raise HTTPException(status_code=400, detail="reference image must be under uploads/")
        reference = str(target)
    try:
        return persona_generator.generate_candidates(
            prompt=payload.prompt,
            count=payload.count,
            aspect_ratio=payload.aspect_ratio,
            reference_path=reference,
            model=payload.model,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"image generation failed: {exc}") from exc


@app.get("/api/personas/{persona_id}")
def get_persona(persona_id: str) -> dict[str, Any]:
    persona = persona_store.load_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"persona": persona}


@app.patch("/api/personas/{persona_id}")
def patch_persona(persona_id: str, payload: PersonaPayload) -> dict[str, Any]:
    if persona_store.load_persona(persona_id) is None:
        raise HTTPException(status_code=404, detail="persona not found")
    try:
        persona = persona_store.save_persona(payload.model_dump(exclude_unset=True), persona_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"persona": persona}


@app.delete("/api/personas/{persona_id}")
def remove_persona(persona_id: str) -> dict[str, Any]:
    return {"removed": persona_store.delete_persona(persona_id)}


@app.get("/api/models")
def list_model_profiles(capability: str | None = None) -> dict[str, Any]:
    return {"models": model_caps.list_profiles(capability=capability)}


@app.get("/api/models/{profile_id}/preflight")
def preflight_model(
    profile_id: str,
    resolution: str | None = None,
    duration: float | None = None,
    operation: str | None = None,
    references: int = 0,
) -> dict[str, Any]:
    return model_caps.preflight(
        profile_id,
        resolution=resolution,
        duration=duration,
        operation=operation,
        references=references,
    )


@app.get("/api/products")
def list_products(include_archived: bool = False) -> dict[str, Any]:
    return {"products": product_store.list_products(include_archived=include_archived)}


@app.post("/api/products")
def create_product(payload: ProductPayload) -> dict[str, Any]:
    try:
        product = product_store.save_product(payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product}


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    product = product_store.load_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"product": product}


@app.patch("/api/products/{product_id}")
def patch_product(product_id: str, payload: ProductPayload) -> dict[str, Any]:
    if product_store.load_product(product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")
    try:
        product = product_store.save_product(payload.model_dump(exclude_unset=True), product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"product": product}


@app.delete("/api/products/{product_id}")
def remove_product(product_id: str) -> dict[str, Any]:
    return {"removed": product_store.delete_product(product_id)}


@app.post("/api/projects/{project_id}/digital-human/plan")
def plan_digital_human(project_id: str, payload: DigitalHumanPayload) -> dict[str, Any]:
    try:
        take = digital_human.plan(project_id, **payload.model_dump(exclude_unset=True))
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"shot/version not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"take": take}


@app.get("/api/formats")
def list_formats() -> dict[str, Any]:
    return {"formats": formats.list_formats()}


@app.post("/api/projects/{project_id}/pipeline/complete")
def complete_pipeline_render(project_id: str, payload: PipelineCompletePayload) -> dict[str, Any]:
    try:
        return pipeline_runner.complete_render(
            project_id,
            payload.version_id,
            payload.render_path,
            approved=payload.approve,
            product_id=payload.product_id,
        )
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"complete render failed: {exc}") from exc


@app.get("/api/brands")
def list_brands() -> dict[str, Any]:
    return {"brands": project_store.list_brands()}


@app.post("/api/brands")
def create_brand(payload: BrandPayload) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    try:
        brand = project_store.save_brand(fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"brand": brand}


@app.get("/api/brands/{brand_id}")
def get_brand(brand_id: str) -> dict[str, Any]:
    brand = project_store.load_brand(brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="brand not found")
    return {"brand": brand}


@app.patch("/api/brands/{brand_id}")
def patch_brand(brand_id: str, payload: BrandPayload) -> dict[str, Any]:
    if project_store.load_brand(brand_id) is None:
        raise HTTPException(status_code=404, detail="brand not found")
    fields = payload.model_dump(exclude_unset=True)
    try:
        brand = project_store.save_brand(fields, brand_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"brand": brand}


@app.delete("/api/brands/{brand_id}")
def remove_brand(brand_id: str) -> dict[str, Any]:
    return {"removed": project_store.delete_brand(brand_id)}


@app.post("/api/brands/{brand_id}/default")
def make_brand_default(brand_id: str) -> dict[str, Any]:
    try:
        brand = project_store.set_default_brand(brand_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="brand not found") from exc
    return {"brand": brand}


@app.post("/api/brands/{brand_id}/apply")
def apply_brand_to_project(brand_id: str, payload: ApplyBrandPayload) -> dict[str, Any]:
    try:
        project = project_store.apply_brand(payload.project_id, brand_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project": project}


SESSIONS_DIR = secrets_store.app_data_dir() / "sessions"


def _session_files() -> list[Path]:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _session_summary(path: Path) -> dict[str, Any]:
    """Read the first record and the first user message; never trust the whole file."""
    head = {"id": path.stem, "cwd": None, "at": None}
    title = ""
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for index, line in enumerate(fh):
                if index > 80:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "session":
                    head["id"] = rec.get("id") or head["id"]
                    head["cwd"] = rec.get("cwd")
                    head["at"] = rec.get("timestamp")
                elif rec.get("type") == "message" and not title:
                    msg = rec.get("message") or {}
                    if msg.get("role") == "user":
                        text = "".join(c.get("text", "") for c in msg.get("content") or [] if c.get("type") == "text")
                        title = text.strip()
    except OSError:
        pass
    stat = path.stat()
    return {
        "path": str(path),
        "id": head["id"],
        "title": (title[:40] + "…") if len(title) > 40 else (title or "未命名会话"),
        "updated": stat.st_mtime,
        "bytes": stat.st_size,
    }


@app.get("/api/sessions")
def list_sessions() -> dict[str, Any]:
    rows = []
    for path in _session_files()[:50]:
        row = _session_summary(path)
        entry = HUB._sessions.get(row["id"])
        row["running"] = bool(entry and entry["bridge"].alive() and entry["bridge"].running)
        rows.append(row)
    return {"sessions": rows, "dir": str(SESSIONS_DIR)}


@app.post("/api/sessions")
def new_session() -> dict[str, Any]:
    import uuid as _uuid

    return {"session_id": f"om-{_uuid.uuid4().hex[:8]}"}


_DIM_CACHE: dict[str, tuple[int, int]] = {}


def _probe_dims(paths: list[Path]) -> dict[str, tuple[int, int]]:
    """Width/height per render, so the UI can show the poster at its true aspect."""
    import re

    out: dict[str, tuple[int, int]] = {}
    ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
    for path in paths:
        key = f"{path}:{path.stat().st_mtime}"
        if key in _DIM_CACHE:
            out[str(path)] = _DIM_CACHE[key]
            continue
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
                capture_output=True, text=True, timeout=20,
            )
            match = re.search(r"(\d+)x(\d+)", proc.stdout or "")
            if match:
                dim = (int(match.group(1)), int(match.group(2)))
                _DIM_CACHE[key] = dim
                out[str(path)] = dim
        except (OSError, subprocess.SubprocessError):
            continue
    return out


@app.get("/api/workspace")
def workspace() -> dict[str, Any]:
    """Latest project + pipeline state + renders, for the workspace shell."""
    root = config_store.output_dir()
    projects = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True) if root.is_dir() else []
    if not projects:
        return {"project": None, "stages": [], "renders": []}
    project = projects[0]
    marker = project / "project.json"
    title, pipeline = project.name, None
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            title = data.get("title") or title
            pipeline = data.get("pipeline_type")
        except json.JSONDecodeError:
            pass
    try:
        import adplus  # noqa: F401 — vendor on sys.path
        from lib.checkpoint import get_completed_stages, get_pipeline_stages

        stages_all = get_pipeline_stages(pipeline)
        done = set(get_completed_stages(root, project.name, pipeline))
    except Exception:
        stages_all, done = [], set()
    renders = sorted(
        (p for p in project.rglob("*.mp4") if p.is_file() and ".qa" not in str(p) and "final_review" not in str(p)),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )[:8]
    dims = _probe_dims(renders)
    return {
        "project": {"id": project.name, "title": title, "pipeline": pipeline},
        "stages": [{"name": s, "done": s in done} for s in stages_all],
        "renders": [
            {"path": str(p.relative_to(root.parent)), "name": p.name, "bytes": p.stat().st_size,
             "mtime": p.stat().st_mtime, "width": dims.get(str(p), (0, 0))[0],
             "height": dims.get(str(p), (0, 0))[1]}
            for p in renders
        ],
    }


@app.get("/api/pi/providers")
def pi_providers() -> dict[str, Any]:
    return capabilities.pi_block()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    data = config_store.load()
    notifications = {
        "approvals": bool(data.get("notify_approvals", True)),
        "done": bool(data.get("notify_done", True)),
        "failed": bool(data.get("notify_failed", True)),
    }
    try:
        budget = float(data.get("daily_budget_usd", 2.0))
    except (TypeError, ValueError):
        budget = 2.0
    return {
        "output_dir": str(config_store.output_dir()),
        "default_output_dir": str(config_store.DEFAULT_OUTPUT_DIR),
        "configured": bool(data.get("output_dir")),
        "app_data": str(secrets_store.app_data_dir()),
        "notifications": notifications,
        "daily_budget_usd": budget,
    }


@app.post("/api/config")
def set_config(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "output_dir" in payload:
        raw = str(payload.get("output_dir") or "").strip()
        if raw:
            target = Path(raw).expanduser()
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(status_code=400, detail=f"目录不可用：{exc}") from exc
            if not target.is_dir():
                raise HTTPException(status_code=400, detail="不是目录")
            updates["output_dir"] = str(target)
        else:
            updates["output_dir"] = ""
    for key in ("approvals", "done", "failed"):
        if f"notify_{key}" in payload:
            updates[f"notify_{key}"] = bool(payload[f"notify_{key}"])
    if "daily_budget_usd" in payload:
        try:
            budget = float(payload["daily_budget_usd"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="budget must be a number") from exc
        updates["daily_budget_usd"] = max(0.0, budget)
    if updates:
        config_store.save(updates)
    if "output_dir" in updates:
        config_store.apply_to_env()
    return get_config()


class NotifyPayload(BaseModel):
    title: str = "Ad+"
    body: str = ""


@app.post("/api/notify")
def notify(payload: NotifyPayload) -> dict[str, Any]:
    """macOS system notification via osascript (no extra plugin)."""
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    script = (
        f"display notification {json.dumps(body[:300], ensure_ascii=False)} "
        f"with title {json.dumps(payload.title[:80] or 'Ad+', ensure_ascii=False)}"
    )
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=(proc.stderr or "osascript failed")[:300])
    return {"ok": True}


@app.get("/api/pi/models")
def pi_models(force: bool = False) -> dict[str, Any]:
    models = list_models(force=force)
    payload: dict[str, Any] = {"models": models}
    if not models:
        probe = _pi("--list-models")
        detail = (probe.get("stderr") or probe.get("error") or "").strip()
        payload["error"] = detail[:300] or "pi returned no models"
    return payload


class SessionHub:
    """One live Pi process per session, shared across webview reloads.

    Navigating to /settings used to kill the run because the websocket owned
    the Pi process. The hub keeps the process alive and lets a reconnecting
    page attach to it, replay history through `get_messages`, and keep
    receiving live events.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _prune(self) -> None:
        cutoff = time.time() - 2 * 3600
        for key, entry in list(self._sessions.items()):
            if not entry["subs"] and entry["touched"] < cutoff:
                try:
                    entry["bridge"].close()
                except Exception:
                    pass
                self._sessions.pop(key, None)

    def attach(self, key: str, factory, model: str, loop: asyncio.AbstractEventLoop) -> tuple[dict[str, Any], bool]:
        with self._lock:
            self._prune()
            entry = self._sessions.get(key)
            created = False
            if entry is None or not entry["bridge"].alive():
                bridge = factory()
                entry = {"bridge": bridge, "model": model, "subs": set(), "backlog": deque(maxlen=400),
                         "touched": time.time()}
                self._sessions[key] = entry
                created = True
                threading.Thread(target=self._pump, args=(entry,), name=f"pi-pump-{key}", daemon=True).start()
            entry["touched"] = time.time()
            return entry, created

    def _pump(self, entry: dict[str, Any]) -> None:
        bridge = entry["bridge"]
        while True:
            record = bridge.events.get()
            if record is None:
                break
            entry["backlog"].append(record)
            for into in list(entry["subs"]):
                try:
                    into.put_nowait(record)
                except Exception:
                    pass
        for into in list(entry["subs"]):
            try:
                into.put_nowait(None)
            except Exception:
                pass

    def subscribe(self, entry: dict[str, Any]) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        entry["subs"].add(queue)
        return queue

    def unsubscribe(self, entry: dict[str, Any], queue: asyncio.Queue) -> None:
        entry["subs"].discard(queue)
        entry["touched"] = time.time()

    def drop(self, key: str) -> None:
        with self._lock:
            entry = self._sessions.pop(key, None)
        if entry:
            try:
                entry["bridge"].close()
            except Exception:
                pass


HUB = SessionHub()


@app.post("/api/sessions/{session_id}/stop")
def stop_session(session_id: str) -> dict[str, Any]:
    HUB.drop(session_id)
    return {"ok": True}


def _session_transcript(path: Path) -> list[dict[str, Any]]:
    """Replay a session as turns of text / thinking / tool blocks.

    Mirrors what the live stream shows, so a replayed conversation has the same
    shape as a fresh one (collapsible thinking, collapsible tool groups).
    """
    turns: list[dict[str, Any]] = []
    assistant: dict[str, Any] | None = None
    by_call: dict[str, dict[str, Any]] = {}

    def open_assistant() -> dict[str, Any]:
        nonlocal assistant
        if assistant is None:
            assistant = {"role": "assistant", "blocks": []}
            turns.append(assistant)
        return assistant

    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "message":
                    continue
                msg = rec.get("message") or {}
                role = msg.get("role")
                if role == "system":
                    continue
                parts = [p for p in (msg.get("content") or []) if isinstance(p, dict)]

                if role == "user":
                    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
                    if text:
                        assistant = None
                        turns.append({"role": "user", "text": text})
                elif role == "assistant":
                    if assistant is not None and not assistant["blocks"]:
                        assistant = None          # empty placeholder from a prior record
                    turn = open_assistant()
                    for part in parts:
                        kind = part.get("type")
                        if kind == "thinking":
                            thinking = (part.get("thinking") or "").strip()
                            if thinking:
                                turn["blocks"].append({"kind": "thinking", "text": thinking})
                        elif kind == "text":
                            text = (part.get("text") or "").strip()
                            if text:
                                turn["blocks"].append({"kind": "text", "text": text})
                        elif kind == "toolCall":
                            block = {
                                "kind": "tool",
                                "id": part.get("id") or "",
                                "name": part.get("name") or "tool",
                                "args": str(part.get("arguments") or "")[:600],
                                "result": "",
                                "ok": True,
                                "durationMs": 0,
                            }
                            turn["blocks"].append(block)
                            if block["id"]:
                                by_call[block["id"]] = block
                elif role == "toolResult":
                    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
                    block = by_call.get(msg.get("toolCallId") or "")
                    if block is not None and not block["result"]:
                        block["result"] = text[:1500]
                        block["ok"] = not msg.get("isError")
                        block["durationMs"] = int(msg.get("durationMs") or 0)
    except OSError:
        return []
    return turns


def _session_usage(path: Path) -> dict[str, Any]:
    """Token/cost totals for a session, read from its assistant messages."""
    total = {"input": 0, "output": 0, "cost": 0.0}
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = ((rec.get("message") or {}).get("usage")) or {}
                if not usage:
                    continue
                total["input"] += int(usage.get("input") or 0)
                total["output"] += int(usage.get("output") or 0)
                cost = usage.get("cost")
                if isinstance(cost, dict):
                    total["cost"] += float(cost.get("total") or 0)
                elif isinstance(cost, (int, float)):
                    total["cost"] += float(cost)
    except OSError:
        return total
    return total


@app.get("/api/sessions/messages")
def session_messages(path: str, limit: int = 30, before: int = 0) -> dict[str, Any]:
    root = (Path(__file__).resolve().parent.parent).resolve()
    target = Path(path)
    if not target.is_absolute():
        candidate = (SESSIONS_DIR / path).resolve()
        target = candidate if candidate.is_file() else (root / path).resolve()
    allowed = SESSIONS_DIR.resolve()
    if allowed not in target.parents and target.parent != allowed:
        raise HTTPException(status_code=403, detail="not a session file")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="session not found")
    turns = _session_transcript(target)
    total = len(turns)
    end = total if before <= 0 else max(0, min(total, before))
    start = max(0, end - max(1, min(100, limit)))
    return {
        "messages": turns[start:end],
        "has_more": start > 0,
        "before": start,
        "total": total,
        "usage": _session_usage(target),
    }


@app.get("/api/artifacts")
def session_artifacts(path: str = "", session_id: str = "") -> dict[str, Any]:
    """Files this conversation actually produced (renders, artifacts, assets)."""
    root = (Path(__file__).resolve().parent.parent).resolve()
    files: dict[str, dict[str, Any]] = {}

    MEDIA_EXT = {
        "video": {".mp4", ".mov", ".webm", ".m4v"},
        "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
        "audio": {".mp3", ".wav", ".m4a", ".aac", ".flac"},
        "doc": {".pdf", ".md", ".txt", ".srt", ".vtt"},
    }

    def kind_of(suffix: str) -> str:
        for name, exts in MEDIA_EXT.items():
            if suffix in exts:
                return name
        return "code"

    def add(candidate: Path) -> None:
        try:
            resolved = candidate.resolve()
        except OSError:
            return
        if not resolved.is_file():
            return
        if root not in resolved.parents:
            return
        rel = str(resolved.relative_to(root))
        ext = resolved.suffix.lower()
        files[rel] = {
            "path": rel,
            "name": resolved.name,
            "bytes": resolved.stat().st_size,
            "mtime": resolved.stat().st_mtime,
            "ext": ext,
            "kind": kind_of(ext),
        }

    target = Path(path)
    if target and not target.is_absolute():
        candidate = (SESSIONS_DIR / path).resolve()
        target = candidate if candidate.is_file() else (root / path).resolve()
    if target.is_file():
        try:
            with target.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"toolCall"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for part in (rec.get("message") or {}).get("content") or []:
                        if not isinstance(part, dict) or part.get("type") != "toolCall":
                            continue
                        args = str(part.get("arguments") or "")
                        for token in re.findall(r"[\w./\-]+\.(?:mp4|mov|webm|png|jpe?g|wav|mp3|json|html|js|css)", args):
                            if "projects/" in token:
                                add(root / token)
        except OSError:
            pass

    rank = {"video": 0, "image": 1, "audio": 2, "doc": 3, "code": 4}
    rows = sorted(files.values(), key=lambda r: (rank.get(r["kind"], 9), -r["mtime"]))
    primary = next((r["path"] for r in rows if r["kind"] == "video"), None)
    for r in rows:
        r["primary"] = r["path"] == primary
    return {"files": rows[:80], "counts": {k: sum(1 for r in rows if r["kind"] == k) for k in rank}}


@app.post("/api/reveal")
def reveal(payload: dict[str, Any]) -> dict[str, Any]:
    rel = str(payload.get("path") or "")
    target = (Path(__file__).resolve().parent.parent / rel).resolve()
    roots = [
        (Path(__file__).resolve().parent.parent).resolve(),
        secrets_store.app_data_dir().resolve(),
    ]
    if not any(root == target or root in target.parents for root in roots):
        raise HTTPException(status_code=403, detail="outside allowed roots")
    if not target.exists():
        raise HTTPException(status_code=404, detail="not found")
    subprocess.run(["open", "-R", str(target)], check=False)
    return {"ok": True}


@app.post("/api/trash")
def trash(payload: dict[str, Any]) -> dict[str, Any]:
    rel = str(payload.get("path") or "")
    root = (Path(__file__).resolve().parent.parent).resolve()
    target = (root / rel).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=403, detail="not a workspace file")
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(exist_ok=True)
    dest = trash_dir / target.name
    index = 1
    while dest.exists():
        dest = trash_dir / f"{target.stem} {index}{target.suffix}"
        index += 1
    target.replace(dest)
    return {"ok": True, "moved": str(dest)}


# --------------------------------------------------------------------------- #
# quotes / approvals (the filesystem contract lives in adplus/agent_bridge.py)
# --------------------------------------------------------------------------- #
def _bridge():
    from adplus import agent_bridge

    return agent_bridge


# --------------------------------------------------------------------------- #
# background jobs (renders)
# --------------------------------------------------------------------------- #
def _jobs():
    from adplus import jobs as job_store

    return job_store


def _normalize_output(path: Any) -> Any:
    """Map stale absolute outputs from an older checkout onto this project root."""
    if not path:
        return path
    raw = str(path)
    candidate = Path(raw)
    if candidate.is_file():
        return raw
    marker = "/projects/"
    if marker in raw:
        suffix = raw.split(marker, 1)[1]
        root = Path(_bridge().PROJECTS_DIR)
        moved = root / suffix
        if moved.is_file():
            return str(moved)
    return raw


@app.get("/api/jobs")
def list_jobs(project_id: str = "", limit: int = 20) -> dict[str, Any]:
    store = _jobs()
    rows = store.list_jobs(project_id or None, limit=limit)
    for row in rows:
        row["output"] = _normalize_output(row.get("output"))
    return {"jobs": rows, "running": sum(1 for r in rows if r.get("status") == "running")}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("project_id") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    bridge = _bridge()
    original = bridge.read_record("jobs", project_id, job_id)
    if original is None:
        raise HTTPException(status_code=404, detail="job not found")
    if original.get("status") == "running":
        raise HTTPException(status_code=409, detail="job is still running")
    job = {
        **original,
        "id": bridge.new_id("j"),
        "status": "queued",
        "progress": 0.0,
        "frames_done": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "finished_at": None,
        "error": None,
        "output": None,
        "cancel_requested": False,
        "cost_usd": 0.0,
        "retry_of": job_id,
        "log_tail": ["retry queued — waiting for agent"],
    }
    bridge.write_record("jobs", project_id, job)
    return {"ok": True, "job": job}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("project_id") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    try:
        job = _jobs().request_cancel(project_id, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    return {"ok": True, "job": job}


@app.get("/api/quotes")
def list_quotes(project_id: str = "", status: str = "pending") -> dict[str, Any]:
    bridge = _bridge()
    rows = bridge.pending("quotes", project_id or None) if status == "pending" else []
    return {"quotes": rows}


@app.post("/api/quotes/{quote_id}")
def decide_quote(quote_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    bridge = _bridge()
    project_id = str(payload.get("project_id") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    approved = bool(payload.get("approved"))
    try:
        record = bridge.decide(
            "quotes", project_id, quote_id,
            "approved" if approved else "rejected",
            str(payload.get("comment") or ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="quote not found") from exc
    project = project_store.load_project(project_id)
    if project is not None and project.get("status") in ("draft", "briefing", "quoted"):
        project["status"] = "storyboard" if approved else "briefing"
        project_store.save_project(project)
    return {"ok": True, "quote": record}


@app.get("/api/approvals")
def list_approvals(project_id: str = "", status: str = "pending") -> dict[str, Any]:
    bridge = _bridge()
    rows = bridge.pending("approvals", project_id or None) if status == "pending" else []
    return {"approvals": rows}


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    bridge = _bridge()
    project_id = str(payload.get("project_id") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required")
    approved = bool(payload.get("approved"))
    try:
        record = bridge.decide(
            "approvals", project_id, approval_id,
            "approved" if approved else "rejected",
            str(payload.get("comment") or ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    return {"ok": True, "approval": record}


# live fan-out: the MCP process writes files, we watch and notify every webview
_WATCHERS: set[asyncio.Queue] = set()
_SEEN_PENDING: set[str] = set()


def _broadcast(record: dict[str, Any] | None) -> None:
    for queue in list(_WATCHERS):
        try:
            queue.put_nowait(record)
        except Exception:
            pass


def _pending_events() -> list[dict[str, Any]]:
    bridge = _bridge()
    events: list[dict[str, Any]] = []
    for record in bridge.pending("quotes"):
        events.append({"type": "quote_pending", "record": record})
    for record in bridge.pending("approvals"):
        events.append({"type": "gate_pending", "record": record})
    return events


def _start_watcher() -> None:
    def loop() -> None:
        while True:
            try:
                events = _pending_events()
                fresh = [e for e in events if e["record"]["id"] not in _SEEN_PENDING]
                for event in fresh:
                    _SEEN_PENDING.add(event["record"]["id"])
                    _broadcast(event)
                for event in events:
                    if event["type"] == "quote_pending" and event["record"].get("status") != "pending":
                        _SEEN_PENDING.discard(event["record"]["id"])
            except Exception:
                pass
            time.sleep(1.2)

    threading.Thread(target=loop, name="quote-watcher", daemon=True).start()


_start_watcher()


@app.get("/api/sessions/active")
def active_sessions() -> dict[str, Any]:
    return {"active": [k for k, v in HUB._sessions.items() if v["bridge"].alive()]}


@app.websocket("/ws/chat")
async def chat_socket(ws: WebSocket) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    entry: dict[str, Any] | None = None
    queue: asyncio.Queue | None = None

    async def forward() -> None:
        while True:
            record = await queue.get()
            if record is None:
                return
            await ws.send_json(record)

    notify: asyncio.Queue = asyncio.Queue()

    async def forward_meta() -> None:
        while True:
            event = await notify.get()
            if event is None:
                return
            await ws.send_json(event)

    sender: asyncio.Task | None = None
    meta_sender = asyncio.create_task(forward_meta())
    _WATCHERS.add(notify)
    try:
        await ws.send_json({"type": "ready", "pi": pi_bridge.pi_executable()})
        for event in _pending_events():
            _SEEN_PENDING.add(event["record"]["id"])
            await ws.send_json(event)
        while True:
            message = await ws.receive_json()
            action = message.get("action")
            if action == "start":
                key = message.get("session_id") or message.get("session") or f"anon-{ws.client}"
                provider, model = message.get("provider"), message.get("model")
                cwd = message.get("cwd") or str(adplus.paths.WORKSPACE)

                def factory() -> pi_bridge.PiBridge:
                    return pi_bridge.PiBridge(
                        cwd=cwd, provider=provider, model=model, session_dir=SESSIONS_DIR,
                        session_id=message.get("session_id"), resume_path=message.get("session"),
                    )

                entry, created = HUB.attach(key, factory, f"{provider}/{model}", loop)
                if queue:
                    HUB.unsubscribe(entry, queue)
                queue = HUB.subscribe(entry)
                if sender:
                    sender.cancel()
                sender = asyncio.create_task(forward())
                await ws.send_json({
                    "type": "session",
                    "model": entry["model"],
                    "pid": entry["bridge"].proc.pid,
                    "session_id": message.get("session_id"),
                    "resumed": bool(message.get("session")) or not created,
                    "attached": not created,
                    "running": entry["bridge"].running,
                })
            elif action == "prompt":
                if not entry:
                    await ws.send_json({"type": "error", "message": "start a session first"})
                    continue
                try:
                    request_id = entry["bridge"].prompt(message.get("text", ""))
                    await ws.send_json({"type": "prompt_accepted", "id": request_id})
                except RuntimeError as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
            elif action == "abort":
                if entry:
                    entry["bridge"].abort()
            elif action == "get_messages":
                if entry:
                    entry["bridge"].get_messages()
            elif action == "get_state":
                if entry:
                    entry["bridge"].get_state()
    except WebSocketDisconnect:
        pass
    finally:
        _WATCHERS.discard(notify)
        meta_sender.cancel()
        if sender:
            sender.cancel()
        if entry and queue:
            HUB.unsubscribe(entry, queue)


class RestyleCreatePayload(BaseModel):
    path: str
    title: str | None = None
    rights_confirmed: bool = False


class RestylePlanPayload(BaseModel):
    revision: int | None = None
    patch: dict[str, Any]


@app.get("/api/restyle/backends")
def restyle_backends() -> dict[str, Any]:
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "backends": restyle_segment.available_backends(),
    }


@app.get("/api/restyle")
def restyle_list() -> dict[str, Any]:
    return {"restyles": restyle_store.list_restyles()}


@app.post("/api/restyle")
def restyle_create(payload: RestyleCreatePayload) -> dict[str, Any]:
    try:
        record = restyle_store.create(
            payload.path,
            title=payload.title,
            rights_confirmed=bool(payload.rights_confirmed),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="source video not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"restyle": record}


@app.get("/api/restyle/{project_id}")
def restyle_detail(project_id: str) -> dict[str, Any]:
    record = restyle_store.detail(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="restyle not found")
    return record


@app.post("/api/restyle/{project_id}/analyze")
def restyle_analyze(project_id: str) -> dict[str, Any]:
    try:
        job = restyle_store.start_analysis(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="restyle not found") from exc
    return {"job": job}


@app.patch("/api/restyle/{project_id}/plan")
def restyle_save_plan(project_id: str, payload: RestylePlanPayload) -> dict[str, Any]:
    try:
        plan = restyle_store.save_plan(project_id, payload.patch, payload.revision)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="restyle not found") from exc
    except ValueError as exc:
        if str(exc) == "revision_conflict":
            current = restyle_store.detail(project_id) or {}
            return JSONResponse(
                status_code=409,
                content={"detail": "revision conflict", "plan": current.get("plan")},
            )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"plan": plan}


@app.delete("/api/restyle/{project_id}")
def restyle_delete(project_id: str) -> dict[str, Any]:
    try:
        token = restyle_store.delete(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="restyle not found") from exc
    return {"trash_id": token}


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Cheap liveness probe: must not touch the registry (discovery is slow)."""
    return {"ok": True, "app_data": str(secrets_store.app_data_dir()), "version": app.version}


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
