"""Plan document for a restyle project.

The plan is the user-editable half of the module: cast, scenes, objects,
product, captions, voice and output.  The blueprint (shots, groups, OCR) is
derived from the source video and is read-only.
"""

from __future__ import annotations

import copy
import time
from typing import Any

DEFAULT_OUTPUT = {"aspect": "source", "resolution": "720p", "fps": 30}
DEFAULT_CAPTION_STYLE = {
    "font": "NotoSansSC-Bold",
    "size": 34,
    "fill": "#FFD400",
    "stroke": "#111111",
    "stroke_width": 3,
}
CHANGE_LEVELS = ("light", "recommended", "all")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def default_plan(blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    groups = (blueprint or {}).get("groups") or {}
    outfits = {
        str(item.get("id")): {"mode": "hue", "value": 0}
        for item in groups.get("outfits") or []
        if item.get("id")
    }
    scenes = {
        str(item.get("id")): {"mode": "keep"}
        for item in groups.get("scenes") or []
        if item.get("id")
    }
    objects = {
        str(item.get("id")): {"mode": "keep", "reason": "contact_furniture"}
        for item in groups.get("objects") or []
        if item.get("id")
    }
    return {
        "revision": 1,
        "change_level": "recommended",
        "cast": {
            "persona_id": None,
            "mode": "appearance",
            "outfit_targets": outfits,
            "hair": {"mode": "keep", "value": None},
            "skin": {"mode": "keep", "strength": 0.0},
            "voice": {"mode": "keep", "voice_id": None},
        },
        "scenes": scenes,
        "objects": objects,
        "product": {"mode": "lock", "product_id": None},
        "output": copy.deepcopy(DEFAULT_OUTPUT),
        "captions": {"mode": "keep", "style": copy.deepcopy(DEFAULT_CAPTION_STYLE)},
        "overrides": {},
        "updated_at": _now(),
    }


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def sync_groups(plan: dict[str, Any], blueprint: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Add scene/outfit/object keys discovered by analysis without touching user modes."""
    out = copy.deepcopy(plan)
    groups = (blueprint or {}).get("groups") or {}
    changed = False
    for kind, key, default in (
        ("scenes", "scenes", {"mode": "keep"}),
        ("outfits", "outfit_targets", {"mode": "hue", "value": 0}),
        ("objects", "objects", {"mode": "keep", "reason": "contact_furniture"}),
    ):
        target = out.setdefault(key, {}) if key != "outfit_targets" else out.setdefault("cast", {}).setdefault("outfit_targets", {})
        for item in groups.get(kind) or []:
            item_id = str(item.get("id") or "")
            if item_id and item_id not in target:
                target[item_id] = copy.deepcopy(default)
                changed = True
    if changed:
        out["revision"] = int(out.get("revision") or 0) + 1
        out["updated_at"] = _now()
    return out, changed


def apply_patch(plan: dict[str, Any], patch: dict[str, Any], revision: int | None = None) -> dict[str, Any]:
    if revision is not None and int(revision) != int(plan.get("revision") or 0):
        raise ValueError("revision_conflict")
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    allowed = {
        "change_level", "cast", "scenes", "objects", "product",
        "output", "captions", "overrides",
    }
    unknown = set(patch) - allowed
    if unknown:
        raise ValueError(f"unknown plan fields: {sorted(unknown)}")
    level = patch.get("change_level", plan.get("change_level"))
    if level not in CHANGE_LEVELS:
        raise ValueError(f"change_level must be one of {CHANGE_LEVELS}")
    merged = _merge(plan, patch)
    merged["change_level"] = level
    merged["revision"] = int(plan.get("revision") or 0) + 1
    merged["updated_at"] = _now()
    return merged
