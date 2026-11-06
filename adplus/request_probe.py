"""Build a provider request without sending it.

This is a contract probe, not a quality test.  It answers questions that do
not need a valid key:

- is the endpoint/model correct?
- are duration/resolution/aspect supported?
- are the reference images actually embedded?
- is a product/presenter binding present?
- would the provider reject a parameter before spending money?

Adapters use the same tool classes as execution, so a probe drift is a real
integration bug rather than a second hand-written payload.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from adplus import capabilities

SENSITIVE = ("authorization", "api_key", "apikey", "token", "secret", "password")


def _tool(name: str):
    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get(name)
    if tool is None:
        raise ValueError(f"OpenMontage tool not registered: {name}")
    return tool


def _redact(value: Any, key: str = "") -> Any:
    if key and any(part in key.lower() for part in SENSITIVE):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:") and ";base64," in value:
            return f"<data-uri:{len(value)} chars>"
        if len(value) > 512 and any(ch in value for ch in "+/=") and "\n" not in value:
            return f"<inline-media:{len(value)} chars>"
    return value


def _file_input(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    return {"path": str(resolved), "exists": resolved.is_file(), "bytes": resolved.stat().st_size if resolved.is_file() else 0}


def probe(profile_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized, non-executing request description."""
    profile = capabilities.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"unknown model profile: {profile_id}")
    tool_name = profile.get("tool")
    if not tool_name:
        raise ValueError(f"{profile_id} has no tool mapping")
    tool = _tool(str(tool_name))
    payload: dict[str, Any] = {}
    endpoint = ""
    method = "POST"
    error = None
    warnings: list[str] = []
    try:
        if profile_id == "seedance-2.0" or profile_id == "seedance-2.5":
            payload = tool._build_payload(inputs)  # noqa: SLF001 - contract probe
            endpoint = f"{tool._get_base_url()}/contents/generations/tasks"  # noqa: SLF001
        elif profile_id.startswith("minimax"):
            model = str(inputs.get("model") or "MiniMax-Hailuo-2.3-Fast")
            base = tool._base_url()  # noqa: SLF001
            if model == "MiniMax-H3":
                payload, error = tool._build_v2_payload(inputs, base)  # noqa: SLF001
                version = "v2"
            else:
                payload, error = tool._build_v1_payload(inputs, model)  # noqa: SLF001
                version = "v1"
            endpoint = f"{base}/{version}/video_generation"
        elif profile_id == "kling-avatar":
            request = tool._build_request(inputs)  # noqa: SLF001
            payload = request.get("payload") or {}
            endpoint = f"https://api-beijing.klingai.com{request.get('path')}"
        elif profile_id == "heygen-avatar-v":
            payload = tool.build_payload(inputs)
            endpoint = "https://api.heygen.com/v3/videos"
        elif profile_id == "wav2lip":
            endpoint = "local://wav2lip"
            method = "LOCAL"
            payload = {
                "video_path": inputs.get("video_path"),
                "audio_path": inputs.get("audio_path"),
                "model": inputs.get("model") or "wav2lip_gan",
                "output_path": inputs.get("output_path"),
            }
        else:
            raise ValueError(f"no request probe for {profile_id}")
    except Exception as exc:
        error = str(exc)[:500]
    if profile.get("region") == "cn" and "api.minimax.io" in endpoint:
        warnings.append("MiniMax profile 标记为 cn，但请求走 global endpoint；设置 MINIMAX_REGION=cn")
    if profile.get("region") == "cn" and "api-singapore.klingai.com" in endpoint:
        warnings.append("Kling profile 标记为 cn，但请求走 Singapore endpoint；设置 KLING_API_BASE_URL")
    payload = _redact(payload)
    return {
        "profile": profile,
        "tool": tool_name,
        "method": method,
        "endpoint": endpoint,
        "valid": error is None,
        "error": error,
        "warnings": warnings,
        "payload": payload,
        "inputs": {k: _file_input(v) if k.endswith("_path") else _redact(v, k) for k, v in inputs.items()},
        "checks": {
            "model": payload.get("model"),
            "resolution": payload.get("resolution"),
            "duration": payload.get("duration"),
            "aspect_ratio": payload.get("ratio") or payload.get("aspect_ratio"),
            "content_blocks": len(payload.get("content") or []),
            "has_reference_image": any(
                block.get("image_url") is not None or block.get("image") is not None
                for block in (payload.get("content") or [])
                if isinstance(block, dict)
            ),
        },
    }


def probe_avatar(profile_id: str, *, image_path: str, audio_path: str, output_path: str, prompt: str = "") -> dict[str, Any]:
    return probe(profile_id, {
        "image_path": image_path,
        "audio_path": audio_path,
        "sound_file_path": audio_path,
        "output_path": output_path,
        "prompt": prompt,
        "mode": "std",
    })


def probe_video(profile_id: str, *, prompt: str, duration: int, resolution: str, aspect_ratio: str = "9:16", image_path: str | None = None) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "ratio": aspect_ratio,
        "operation": "image_to_video" if image_path else "text_to_video",
    }
    if image_path:
        inputs["reference_image_path"] = image_path
        inputs["image_path"] = image_path
        inputs["first_frame_image"] = image_path
    return probe(profile_id, inputs)
