"""Write OpenMontage-shaped artifacts from Ad+ project state.

Ad+ may keep a storyboard cache, but the canonical production artifacts must be
usable by OpenMontage checkpoints/agents.  This module is the one-way mapping:

    project + version -> brief / script / scene_plan / asset_manifest

It validates against the upstream JSON schemas before writing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from adplus import project_store
from adplus.paths import PROJECTS


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _validate(name: str, payload: dict[str, Any]) -> None:
    from schemas.artifacts import validate_artifact

    validate_artifact(name, payload)


def _path(project_id: str, name: str) -> Path:
    return PROJECTS / project_id / "artifacts" / f"{name}.json"


def write(project_id: str, name: str, payload: dict[str, Any], *, validate: bool = True) -> Path:
    if validate:
        _validate(name, payload)
    path = _path(project_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read(project_id: str, name: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_path(project_id, name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _platform(value: str) -> str:
    mapping = {"douyin": "tiktok", "xiaohongshu": "generic", "bilibili": "generic", "youtube": "youtube"}
    return mapping.get(value, "generic")


def brief_from_project(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    product = str(raw.get("product") or project.get("title") or "商品")
    points = raw.get("selling_points") if isinstance(raw.get("selling_points"), list) else []
    points = [str(item) for item in points if str(item).strip()] or [product]
    return {
        "version": "1.0",
        "title": str(project.get("title") or product),
        "hook": str(raw.get("must_say") or raw.get("description") or product),
        "key_points": points,
        "core_message": str(raw.get("description") or product),
        "cta": str(raw.get("cta") or "点击了解"),
        "tone": str(raw.get("tone") or "clean"),
        "style": "clean-professional",
        "target_audience": str(raw.get("audience") or "通用"),
        "target_platform": _platform(str(project.get("platform") or "generic")),
        "target_duration_seconds": max(1.0, float(project.get("duration_s") or 15)),
        "metadata": {"adplus_project_id": project["project_id"], "route": project.get("route")},
    }


def script_from_version(project: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    script = None
    try:
        from adplus import production
        script = production.script_for(str(project["project_id"]))
    except Exception:
        script = None
    lines = list((script or {}).get("lines") or [])
    shots = version.get("shots") or []
    sections = []
    cursor = 0.0
    for index, line in enumerate(lines):
        duration = float((shots[index].get("duration_s") if index < len(shots) else 0) or 2.5)
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        sections.append({
            "id": str(line.get("id") or f"s{index + 1}"),
            "label": f"Section {index + 1}",
            "text": text,
            "start_seconds": round(cursor, 3),
            "end_seconds": round(cursor + duration, 3),
        })
        cursor += duration
    if not sections:
        sections = [{
            "id": "s1", "label": "Section 1", "text": str(project.get("title") or "商品介绍"),
            "start_seconds": 0.0, "end_seconds": max(1.0, float(version.get("duration_s") or 10)),
        }]
        cursor = sections[0]["end_seconds"]
    return {
        "version": "1.0",
        "title": str(project.get("title") or "Untitled"),
        "total_duration_seconds": round(max(cursor, 1.0), 3),
        "voice_performance": {"pacing_profile": "conversational", "performance_intent": "natural product explanation"},
        "sections": sections,
    }


def scene_plan_from_version(project: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    scenes = []
    for shot in version.get("shots") or []:
        method = str(shot.get("production_method") or "source_video")
        kind = "generated" if method in {"image_to_video", "reference_to_video"} else "talking_head"
        scene = {
            "id": str(shot.get("id") or f"s{len(scenes) + 1}"),
            "type": kind,
            "description": str(shot.get("description") or shot.get("on_screen_text") or "镜头"),
            "start_seconds": float(shot.get("start_s") or 0),
            "end_seconds": float(shot.get("end_s") or 0),
            "transition_in": str(shot.get("transition_in") or ""),
            "transition_out": str(shot.get("transition_out") or ""),
        }
        language = shot.get("shot_language") if isinstance(shot.get("shot_language"), dict) else {}
        if language:
            scene["shot_language"] = {
                key: language[key]
                for key in ("shot_size", "camera_movement", "lens_mm", "lighting_key", "depth_of_field", "color_temperature")
                if key in language
            }
        scenes.append(scene)
    if not scenes:
        scenes = [{
            "id": "s1", "type": "talking_head", "description": "主播口播",
            "start_seconds": 0.0, "end_seconds": max(1.0, float(version.get("duration_s") or 10)),
        }]
    return {"version": "1.0", "style_playbook": "clean-professional", "scenes": scenes}


def asset_manifest_from_version(project: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    assets = []
    for shot in version.get("shots") or []:
        preview = shot.get("preview")
        if not preview:
            continue
        path = str(preview)
        suffix = Path(path).suffix.lower()
        kind = "video" if suffix in {".mp4", ".mov", ".webm"} else "image"
        assets.append({
            "id": f"a_{shot.get('id')}",
            "type": kind,
            "path": path,
            "source_tool": "adplus",
            "scene_id": str(shot.get("id") or ""),
        })
    return {"version": "1.0", "assets": assets, "total_cost_usd": float(version.get("cost_usd") or 0), "metadata": {"adplus_project_id": project["project_id"]}}


def sync_project(project_id: str, version_id: str | None = None) -> dict[str, Any]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    version = project_store.load_version(project_id, version_id) if version_id else project_store.ensure_version(project_id)
    if version is None:
        raise FileNotFoundError("version not found")
    outputs = {}
    for name, payload in {
        "brief": brief_from_project(project),
        "script": script_from_version(project, version),
        "scene_plan": scene_plan_from_version(project, version),
        "asset_manifest": asset_manifest_from_version(project, version),
    }.items():
        outputs[name] = str(write(project_id, name, payload))
    return {"project_id": project_id, "version_id": version["id"], "artifacts": outputs, "synced_at": _now()}
