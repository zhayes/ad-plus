"""Model capabilities and preflight for Ad+.

A route is a production pipeline; a model is a replaceable capability inside
it.  This module is the single registry both quote and UI should read instead
of hard-coding "hybrid unavailable" or "key exists => model works".

It is deliberately conservative:

* a configured key only means the provider is *reachable*;
* a profile can be marked ``blocked`` with a short-lived health record after a
  provider error such as ``ModelNotOpen`` or a content-policy rejection;
* preflight validates resolution / duration / references before a paid call.
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Any

from adplus.paths import STATE_DIR

VIDEO = "video_generation"
AVATAR = "avatar"
LIP_SYNC = "lip_sync"

PROFILES: list[dict[str, Any]] = [
    {
        "id": "minimax-hailuo-2.3-fast",
        "tool": "minimax_video",
        "label": "MiniMax Hailuo 2.3 Fast",
        "provider": "minimax",
        "capability": VIDEO,
        "kind": "image_to_video",
        "region": "cn",
        "requires": ["MINIMAX_API_KEY"],
        "resolutions": ["768P", "1080P"],
        "durations": [6, 10],
        "native_audio": False,
        "reference_images": 1,
        "supports": ["image_to_video", "text_to_video"],
        "cost_note": "按次计费；480P 交付需后期缩放",
    },
    {
        "id": "seedance-2.0",
        "tool": "seedance_ark",
        "label": "豆包 Seedance 2.0",
        "provider": "ark",
        "capability": VIDEO,
        "kind": "image_to_video",
        "region": "cn",
        "requires": ["ARK_API_KEY"],
        "model": "doubao-seedance-2-0-260128",
        "resolutions": ["480p", "720p", "1080p", "4k"],
        "durations": [4, 15],
        "native_audio": False,
        "reference_images": 1,
        "supports": ["image_to_video", "text_to_video"],
        "cost_note": "480p 原生输出；小字/商品标签仍需真实素材兜底",
    },
    {
        "id": "seedance-2.5",
        "tool": "seedance_ark",
        "label": "豆包 Seedance 2.5",
        "provider": "ark",
        "capability": VIDEO,
        "kind": "reference_to_video",
        "region": "cn",
        "requires": ["ARK_API_KEY"],
        "model": "doubao-seedance-2-5-260628",
        "resolutions": ["480p", "720p"],
        "durations": [4, 30],
        "native_audio": True,
        "reference_images": 9,
        "reference_videos": 3,
        "reference_audios": 3,
        "supports": ["image_to_video", "text_to_video", "reference_to_video"],
        "cost_note": "自定义价格；需在报价前配置每百万 token 单价",
    },
    {
        "id": "heygen-avatar-v",
        "tool": "heygen_avatar",
        "label": "HeyGen Avatar V",
        "provider": "heygen",
        "capability": AVATAR,
        "kind": "avatar",
        "region": "global",
        "requires": ["HEYGEN_API_KEY"],
        "resolutions": ["720p", "1080p", "4k"],
        "durations": [0, 600],
        "native_audio": True,
        "lip_sync": True,
        "supports": ["avatar", "lip_sync"],
        "cost_note": "需要先在 HeyGen 后台创建 avatar look",
    },
    {
        "id": "kling-avatar",
        "tool": "kling_avatar",
        "label": "Kling Avatar",
        "provider": "kling_official",
        "capability": AVATAR,
        "kind": "avatar",
        "region": "cn",
        "requires": ["KLING_API_KEY"],
        "resolutions": ["720p", "1080p"],
        "durations": [0, 300],
        "native_audio": True,
        "lip_sync": True,
        "supports": ["avatar", "lip_sync"],
        "cost_note": "官方账号按量计费",
    },
    {
        "id": "wav2lip",
        "tool": "lip_sync",
        "label": "Wav2Lip（本地）",
        "provider": "local",
        "capability": LIP_SYNC,
        "kind": "lip_sync",
        "region": "local",
        "requires": ["WAV2LIP_PATH"],
        "resolutions": ["480p", "720p", "1080p"],
        "durations": [0, 600],
        "native_audio": False,
        "lip_sync": True,
        "supports": ["lip_sync"],
        "cost_note": "免费，但要单独安装模型权重；只改嘴",
    },
    {
        "id": "sadtalker",
        "tool": "talking_head",
        "label": "SadTalker（本地）",
        "provider": "local",
        "capability": AVATAR,
        "kind": "avatar",
        "region": "local",
        "requires": ["SADTALKER_PATH"],
        "resolutions": ["480p", "720p"],
        "durations": [0, 300],
        "native_audio": False,
        "lip_sync": True,
        "supports": ["avatar", "lip_sync"],
        "cost_note": "免费；画质和自然度有限",
    },
]

_BY_ID = {item["id"]: item for item in PROFILES}


def _health_path() -> Path:
    return STATE_DIR / "model_health.json"


def _load_health() -> dict[str, Any]:
    try:
        data = json.loads(_health_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_health(data: dict[str, Any]) -> None:
    _health_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _health_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_health_path())


def record_health(profile_id: str, status: str, code: str = "", message: str = "", ttl_seconds: int = 3600) -> dict[str, Any]:
    """Remember a provider failure without turning it into a permanent config."""
    if profile_id not in _BY_ID:
        raise ValueError(f"unknown model profile: {profile_id}")
    data = _load_health()
    data[profile_id] = {
        "status": status,
        "code": code,
        "message": message,
        "checked_at": time.time(),
        "expires_at": time.time() + max(60, int(ttl_seconds)),
    }
    _save_health(data)
    return data[profile_id]


def clear_health(profile_id: str | None = None) -> None:
    data = _load_health()
    if profile_id:
        data.pop(profile_id, None)
    else:
        data = {}
    _save_health(data)


def _active_health(profile_id: str) -> dict[str, Any] | None:
    record = _load_health().get(profile_id)
    if not isinstance(record, dict):
        return None
    if float(record.get("expires_at") or 0) <= time.time():
        return None
    return record


def _configured(profile: dict[str, Any]) -> bool:
    requires = profile.get("requires") or []
    return all(bool(os.environ.get(name)) for name in requires)


def profile_view(profile: dict[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(profile)
    configured = _configured(profile)
    health = _active_health(str(profile["id"]))
    view["configured"] = configured
    view["health"] = health
    if health:
        view["status"] = "blocked"
        view["status_reason"] = health.get("message") or health.get("code") or "provider blocked"
    elif not configured:
        view["status"] = "unconfigured"
        view["status_reason"] = "缺少 " + ", ".join(profile.get("requires") or [])
    else:
        view["status"] = "available"
        view["status_reason"] = ""
    return view


def list_profiles(capability: str | None = None) -> list[dict[str, Any]]:
    rows = [profile_view(item) for item in PROFILES]
    if capability:
        rows = [row for row in rows if row.get("capability") == capability]
    return rows


def get_profile(profile_id: str) -> dict[str, Any] | None:
    profile = _BY_ID.get(profile_id)
    return profile_view(profile) if profile else None


def preflight(
    profile_id: str,
    *,
    resolution: str | None = None,
    duration: float | None = None,
    operation: str | None = None,
    references: int = 0,
) -> dict[str, Any]:
    profile = _BY_ID.get(profile_id)
    if profile is None:
        return {"ok": False, "status": "unknown", "blockers": [f"unknown model profile: {profile_id}"], "warnings": []}
    view = profile_view(profile)
    blockers: list[str] = []
    warnings: list[str] = []
    if view["status"] == "unconfigured":
        blockers.append(str(view["status_reason"]))
    if view["status"] == "blocked":
        blockers.append(str(view["status_reason"]))
    if operation and operation not in (profile.get("supports") or []):
        blockers.append(f"{profile_id} does not support {operation}")
    if resolution and str(resolution) not in (profile.get("resolutions") or []):
        blockers.append(f"{profile_id} does not support {resolution}")
    if duration is not None:
        low, high = (profile.get("durations") or [0, 0])[:2]
        if not (float(low) <= float(duration) <= float(high)):
            blockers.append(f"{profile_id} duration must be {low}-{high}s")
    max_refs = int(profile.get("reference_images") or 1)
    if references > max_refs:
        blockers.append(f"{profile_id} accepts at most {max_refs} reference images")
    if profile_id == "seedance-2.5":
        warnings.append("Seedance 2.5 uses custom token pricing; configure a price before quoting")
    return {
        "ok": not blockers,
        "status": "ready" if not blockers else ("blocked" if view["status"] in {"blocked", "unconfigured"} else "invalid"),
        "profile": view,
        "blockers": blockers,
        "warnings": warnings,
    }
