"""Digital-human take planning and local/provider adapters.

This is deliberately a thin execution layer over OpenMontage tools:

    persona + audio + shot -> preflight -> take plan -> adapter
    kling-avatar | heygen-avatar-v | wav2lip | sadtalker

It does not pretend a still image can lip-sync by itself.  A take is blocked
until the selected profile has a real adapter and its provider health is good.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from adplus import capabilities, jobs, local_tools, personas, products, project_store
from adplus.paths import PROJECTS

TAKE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

ADAPTER_TOOLS = {
    "kling-avatar": "kling_avatar",
    "wav2lip": "lip_sync",
    "heygen-avatar-v": "heygen_avatar",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _workspace_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECTS.parent / path
    return path.resolve()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECTS.parent.resolve()))
    except (ValueError, OSError):
        return str(path)


def _find_shot(project_id: str, version_id: str | None, shot_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    version = project_store.load_version(project_id, version_id) if version_id else project_store.ensure_version(project_id)
    if version is None:
        raise FileNotFoundError("version not found")
    shot = next((item for item in version.get("shots") or [] if str(item.get("id")) == shot_id), None)
    if shot is None:
        raise KeyError(shot_id)
    return project, version, shot  # type: ignore[return-value]


def plan(
    project_id: str,
    *,
    shot_id: str,
    profile_id: str,
    persona_id: str | None = None,
    product_id: str | None = None,
    version_id: str | None = None,
    audio_path: str | None = None,
    video_path: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Resolve assets and return a blocked/ready take without spending money."""
    project, version, shot = _find_shot(project_id, version_id, shot_id)
    local_tools.ensure_local_tools()
    profile = capabilities.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"unknown model profile: {profile_id}")

    persona_id = persona_id or shot.get("persona_id") or project.get("persona_id")
    product_id = product_id or shot.get("product_id") or project.get("product_id")
    persona = personas.load_persona(persona_id) if persona_id else None
    product = products.load_product(product_id) if product_id else None

    spec = shot.get("generation_spec") if isinstance(shot.get("generation_spec"), dict) else {}
    refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    audio_path = audio_path or spec.get("audio_path") or refs.get("audio")
    video_path = video_path or spec.get("video_path") or refs.get("source_video")
    audio = _workspace_path(str(audio_path)) if audio_path else None
    video = _workspace_path(str(video_path)) if video_path else None
    persona_image = _workspace_path(str(persona.get("source_path"))) if persona and persona.get("source_path") else None
    product_image = _workspace_path(str(product.get("hero_path"))) if product and product.get("hero_path") else None

    blockers: list[str] = []
    warnings: list[str] = []
    operation = "lip_sync" if profile.get("capability") == "lip_sync" else "avatar"
    preflight = capabilities.preflight(profile_id, operation=operation)
    blockers.extend(preflight.get("blockers") or [])

    if persona is None:
        blockers.append("镜头没有绑定数字人/persona")
    else:
        rights = persona.get("rights") or {}
        if not rights.get("ai_allowed"):
            blockers.append("persona 未授权 AI 生成")
        if not rights.get("consent"):
            blockers.append("persona 未确认肖像授权")
        if not persona_image or not persona_image.is_file():
            blockers.append("persona 没有人像源文件")

    if product is not None:
        rights = product.get("rights") or {}
        if not rights.get("ai_reference_allowed"):
            blockers.append("商品未授权 AI 参考")
        if product.get("locked") and not product_image:
            blockers.append("锁定商品缺少真实主图")
        if product_image and not product_image.is_file():
            blockers.append("商品主图文件不存在")

    if profile_id in {"kling-avatar", "sadtalker"}:
        if not audio or not audio.is_file():
            blockers.append("缺少口播音频")
        if not persona_image:
            blockers.append("缺少数字人人像")
    elif profile_id == "wav2lip":
        if not video or not video.is_file():
            blockers.append("Wav2Lip 需要源视频")
        if not audio or not audio.is_file():
            blockers.append("Wav2Lip 需要音频")
    elif profile_id == "heygen-avatar-v":
        if not (persona.get("providers") or {}).get("heygen_avatar_id"):
            blockers.append("persona 缺少 HeyGen avatar_id")
        if not (audio or prompt or shot.get("narration")):
            blockers.append("HeyGen 需要音频或脚本文案")
        warnings.append("HeyGen 需要已创建 avatar look；成本按账号报价")
    else:
        blockers.append(f"{profile_id} 还没有数字人 adapter")

    output = PROJECTS / project_id / "renders" / f"dh_{shot_id}_{profile_id}_{uuid.uuid4().hex[:6]}.mp4"
    take = {
        "id": f"t_{uuid.uuid4().hex[:10]}",
        "project_id": project_id,
        "version_id": version["id"],
        "shot_id": shot_id,
        "profile_id": profile_id,
        "persona_id": persona_id,
        "product_id": product_id,
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "warnings": warnings,
        "profile": profile,
        "tool": ADAPTER_TOOLS.get(profile_id),
        "persona": personas.persona_snapshot(persona_id),
        "product": products.product_snapshot(product_id),
        "input": {
            "persona_image": _rel(persona_image) if persona_image else None,
            "product_image": _rel(product_image) if product_image else None,
            "audio_path": _rel(audio) if audio else None,
            "video_path": _rel(video) if video else None,
            "prompt": prompt or str(shot.get("narration") or shot.get("description") or ""),
        },
        "output_path": _rel(output),
        "created_at": _now(),
        "updated_at": _now(),
        "result": None,
    }
    return take


def _record_provider_failure(profile_id: str, error: str) -> None:
    lowered = str(error).lower()
    if "modelnotopen" in lowered or "not activated" in lowered:
        capabilities.record_health(profile_id, "blocked", "ModelNotOpen", str(error)[:400], ttl_seconds=3600)
    elif "sensitive" in lowered or "copyright" in lowered or "policy" in lowered:
        capabilities.record_health(profile_id, "blocked", "PolicyViolation", str(error)[:400], ttl_seconds=6 * 3600)


def execute(take: dict[str, Any]) -> dict[str, Any]:
    """Run one ready take.  Returns the persisted take; never hides provider errors."""
    if take.get("status") != "ready":
        raise ValueError("take is blocked: " + "; ".join(take.get("blockers") or []))
    profile_id = str(take["profile_id"])
    input_ = take.get("input") or {}
    output = _workspace_path(str(take["output_path"]))
    assert output is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    prompt = str(input_.get("prompt") or "")

    tool_name = ADAPTER_TOOLS.get(profile_id)
    if not tool_name:
        raise ValueError(f"{profile_id} has no digital-human adapter")

    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get(tool_name)
    if tool is None:
        raise ValueError(f"OpenMontage tool not registered: {tool_name}")

    if profile_id == "kling-avatar":
        result = tool.execute({
            "image_path": input_["persona_image"],
            "audio_path": input_["audio_path"],
            "mode": "std",
            "prompt": prompt,
            "output_path": str(output),
            "timeout_seconds": 600,
        })
    elif profile_id == "wav2lip":
        result = tool.execute({
            "video_path": input_["video_path"],
            "audio_path": input_["audio_path"],
            "output_path": str(output),
            "model": "wav2lip_gan",
        })
    elif profile_id == "heygen-avatar-v":
        avatar_id = (take.get("persona") or {}).get("providers", {}).get("heygen_avatar_id")
        result = tool.execute({
            "operation": "generate",
            "avatar_id": avatar_id,
            "script": prompt,
            "engine": "avatar_v",
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "output_path": str(output),
        })
    else:
        raise ValueError(f"{profile_id} has no digital-human adapter")

    take = dict(take)
    take["status"] = "ready" if getattr(result, "success", False) else "failed"
    take["result"] = {
        "success": bool(getattr(result, "success", False)),
        "error": getattr(result, "error", None),
        "output": str(getattr(result, "data", {}).get("output") or output),
        "cost_usd": getattr(result, "cost_usd", None),
    }
    if not take["result"]["success"]:
        _record_provider_failure(profile_id, str(take["result"]["error"] or ""))
    return take
