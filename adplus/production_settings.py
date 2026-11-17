"""Project-level production settings (schema v2).

Ad+ domain configuration, not a pipeline.  Audio and visual concerns are
separate so changing a voice does not invalidate a rendered shot, and changing
a video model does not rerun TTS.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

SCHEMA_VERSION = 2
ASPECTS = ("9:16", "16:9", "1:1")
RESOLUTIONS = ("480p", "720p", "1080p")
FPS = (24, 30)
AUDIO_MODES = ("external_tts", "model_native", "silent")
AUDIO_PROVIDERS = ("local", "minimax", "elevenlabs", "heygen")
AUDIO_FITS = ("trim", "pad", "stretch")
MODES = ("auto", "manual")
VOICE_SOURCES = ("persona", "project", "model")
TIERS = ("draft", "standard", "premium")
ROUTES = ("local_motion", "avatar_spokesperson", "hybrid")

ROUTE_DEFAULTS: dict[str, dict[str, Any]] = {
    "local_motion": {
        "talking_head_profile": None,
        "broll_profile": None,
        "audio_mode": "silent",
    },
    "avatar_spokesperson": {
        "talking_head_profile": "wav2lip",
        "broll_profile": "seedance-2.0",
        "audio_mode": "external_tts",
    },
    "hybrid": {
        "talking_head_profile": "wav2lip",
        "broll_profile": "seedance-2.0",
        "audio_mode": "external_tts",
    },
}


def _route_id(project: dict[str, Any]) -> str:
    raw = project.get("route")
    route = raw.get("id") if isinstance(raw, dict) else str(raw or "")
    if route in ROUTES:
        return route
    pipeline = str(project.get("pipeline_type") or "")
    if pipeline == "avatar-spokesperson":
        return "avatar_spokesperson"
    if pipeline == "hybrid":
        return "hybrid"
    return "local_motion"


def _tier(project: dict[str, Any]) -> str:
    tier = str(project.get("quality_tier") or "standard")
    return tier if tier in TIERS else "standard"


def _default_resolution(project: dict[str, Any]) -> str:
    return "720p" if _tier(project) in {"standard", "premium"} else "480p"


def default_settings(project: dict[str, Any]) -> dict[str, Any]:
    route_id = _route_id(project)
    defaults = ROUTE_DEFAULTS[route_id]
    brief = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    budget = brief.get("budget_usd")
    audio_mode = str(defaults["audio_mode"])
    total = float(budget) if budget not in (None, "") else 2.0
    settings = {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "revisions": {"audio": 1, "visual": 1},
        "format_id": project.get("format_id"),
        "route_id": route_id,
        "output": {
            "platform": project.get("platform") or "douyin",
            "aspect": project.get("aspect") or "9:16",
            "duration_s": float(project.get("duration_s") or 15),
            "resolution": _default_resolution(project),
            "fps": 30,
            "captions": True,
        },
        "audio": {
            "mode": audio_mode,
            "provider": "local" if audio_mode == "external_tts" else "",
            "voice_id": "Tingting" if audio_mode == "external_tts" else "",
            "language": "zh-CN",
            "speed": 1.0,
            "fit": "trim",
            "generate_before_video": audio_mode == "external_tts",
        },
        "visual": {
            "mode": "auto",
            "talking_head_profile": defaults["talking_head_profile"],
            "broll_profile": defaults["broll_profile"],
            "product_profile": defaults["broll_profile"],
            "allow_fallback": False,
            "quality_tier": _tier(project),
        },
        "budget": {
            "total_usd": total,
            "audio_usd": round(total * 0.1, 4),
            "video_usd": round(total * 0.9, 4),
        },
    }
    return _with_aliases(settings)


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        elif value is not None or key not in out:
            out[key] = copy.deepcopy(value)
    return out


def _with_aliases(settings: dict[str, Any]) -> dict[str, Any]:
    """Compatibility aliases for code/UI not yet on v2."""
    audio = settings.setdefault("audio", {})
    visual = settings.setdefault("visual", {})
    budget = settings.setdefault("budget", {})
    settings["generation"] = {
        "mode": visual.get("mode") or "auto",
        "talking_head_profile": visual.get("talking_head_profile"),
        "broll_profile": visual.get("broll_profile"),
        "audio_mode": audio.get("mode") or "silent",
        "allow_fallback": bool(visual.get("allow_fallback")),
        "quality_tier": visual.get("quality_tier") or "draft",
        "budget_usd": float(budget.get("total_usd") or 0),
    }
    settings["voice"] = {
        "source": "persona" if audio.get("mode") != "model_native" else "model",
        "override": {
            "provider": audio.get("provider"),
            "voice_id": audio.get("voice_id"),
            "language": audio.get("language"),
            "speed": audio.get("speed"),
        },
    }
    return settings


def _coerce_resolution(value: Any) -> str:
    """Map a pixel size ("1080x1920") onto the 480p/720p/1080p tiers."""
    match = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*", str(value or ""), re.IGNORECASE)
    if not match:
        return str(value or "")
    short_side = min(int(match.group(1)), int(match.group(2)))
    return "1080p" if short_side >= 1080 else "720p" if short_side >= 720 else "480p"


def _coerce_v2(settings: dict[str, Any]) -> dict[str, Any]:
    """Map legacy generation/voice fields into audio/visual/budget."""
    out = copy.deepcopy(settings)
    legacy_gen = out.get("generation") if isinstance(out.get("generation"), dict) else {}
    legacy_voice = out.get("voice") if isinstance(out.get("voice"), dict) else {}
    override = legacy_voice.get("override") if isinstance(legacy_voice.get("override"), dict) else {}

    audio = out.get("audio") if isinstance(out.get("audio"), dict) else {}
    if not audio:
        audio = {
            "mode": legacy_gen.get("audio_mode") or "silent",
            "provider": override.get("provider") or ("local" if legacy_gen.get("audio_mode") == "external_tts" else ""),
            "voice_id": override.get("voice_id") or ("Tingting" if legacy_gen.get("audio_mode") == "external_tts" else ""),
            "language": override.get("language") or "zh-CN",
            "speed": override.get("speed") or 1.0,
            "fit": "trim",
            "generate_before_video": legacy_gen.get("audio_mode") == "external_tts",
        }
    else:
        # Fill missing audio members from the legacy fields.
        audio.setdefault("mode", legacy_gen.get("audio_mode") or "silent")
        audio.setdefault("provider", override.get("provider") or "local")
        audio.setdefault("voice_id", override.get("voice_id") or "Tingting")
        audio.setdefault("language", override.get("language") or "zh-CN")
        audio.setdefault("speed", override.get("speed") or 1.0)
        audio.setdefault("fit", "trim")
        audio.setdefault("generate_before_video", audio.get("mode") == "external_tts")
    out["audio"] = audio

    visual = out.get("visual") if isinstance(out.get("visual"), dict) else {}
    if not visual:
        visual = {
            "mode": legacy_gen.get("mode") or "auto",
            "talking_head_profile": legacy_gen.get("talking_head_profile"),
            "broll_profile": legacy_gen.get("broll_profile"),
            "product_profile": legacy_gen.get("broll_profile"),
            "allow_fallback": bool(legacy_gen.get("allow_fallback")),
            "quality_tier": legacy_gen.get("quality_tier") or "draft",
        }
    else:
        visual.setdefault("mode", legacy_gen.get("mode") or "auto")
        visual.setdefault("talking_head_profile", legacy_gen.get("talking_head_profile"))
        visual.setdefault("broll_profile", legacy_gen.get("broll_profile"))
        visual.setdefault("product_profile", visual.get("broll_profile"))
        visual.setdefault("allow_fallback", bool(legacy_gen.get("allow_fallback")))
        visual.setdefault("quality_tier", legacy_gen.get("quality_tier") or "draft")
    out["visual"] = visual

    budget = out.get("budget") if isinstance(out.get("budget"), dict) else {}
    if not budget:
        total = float(legacy_gen.get("budget_usd") or 2.0)
        budget = {"total_usd": total, "audio_usd": round(total * 0.1, 4), "video_usd": round(total * 0.9, 4)}
    else:
        budget.setdefault("total_usd", float(legacy_gen.get("budget_usd") or 2.0))
    out["budget"] = budget
    # Projects written by older tooling may hold a pixel size or a music-only
    # audio mode; map both onto this schema instead of rejecting the project.
    output = out.get("output")
    if isinstance(output, dict):
        output["resolution"] = _coerce_resolution(output.get("resolution"))
    if audio.get("mode") == "music":
        audio["mode"] = "silent"
    revisions = out.get("revisions") if isinstance(out.get("revisions"), dict) else {}
    revisions.setdefault("audio", 1)
    revisions.setdefault("visual", 1)
    out["revisions"] = revisions
    out["schema_version"] = SCHEMA_VERSION
    return out


def normalize_settings(project: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults and keep old projects readable without changing state."""
    base = default_settings(project)
    raw = project.get("production_settings")
    if not isinstance(raw, dict):
        return base
    merged = _merge(base, raw)
    legacy_gen = raw.get("generation") if isinstance(raw.get("generation"), dict) else {}
    legacy_voice = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
    override = legacy_voice.get("override") if isinstance(legacy_voice.get("override"), dict) else {}
    if "visual" not in raw and legacy_gen:
        merged["visual"].update({
            "mode": legacy_gen.get("mode", merged["visual"]["mode"]),
            "talking_head_profile": legacy_gen.get("talking_head_profile", merged["visual"]["talking_head_profile"]),
            "broll_profile": legacy_gen.get("broll_profile", merged["visual"]["broll_profile"]),
            "product_profile": legacy_gen.get("broll_profile", merged["visual"]["product_profile"]),
            "allow_fallback": bool(legacy_gen.get("allow_fallback", merged["visual"]["allow_fallback"])),
            "quality_tier": legacy_gen.get("quality_tier", merged["visual"]["quality_tier"]),
        })
    if "audio" not in raw and (legacy_gen or legacy_voice):
        mode = legacy_gen.get("audio_mode", merged["audio"]["mode"])
        merged["audio"] = {
            "mode": mode,
            "provider": override.get("provider") or ("local" if mode == "external_tts" else ""),
            "voice_id": override.get("voice_id") or ("Tingting" if mode == "external_tts" else ""),
            "language": override.get("language") or "zh-CN",
            "speed": override.get("speed") or 1.0,
            "fit": "trim",
            "generate_before_video": mode == "external_tts",
        }
    if "budget" not in raw and legacy_gen:
        total = float(legacy_gen.get("budget_usd") or merged["budget"]["total_usd"])
        merged["budget"] = {"total_usd": total, "audio_usd": round(total * 0.1, 4), "video_usd": round(total * 0.9, 4)}
    project_route = project.get("route")
    explicit = project_route.get("id") if isinstance(project_route, dict) else str(project_route or "")
    raw_route = raw.get("route_id")
    if explicit in ROUTES:
        merged["route_id"] = explicit
    elif raw_route in ROUTES:
        merged["route_id"] = raw_route
    else:
        merged["route_id"] = _route_id(project)
    merged = _coerce_v2(merged)
    merged["revision"] = max(1, int(merged.get("revision") or 1))
    return validate_settings(merged)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def merge_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a user patch, bump the precise revision(s) only on change."""
    before = normalize_settings({
        "production_settings": current,
        "route": {"id": current.get("route_id")},
    })
    changed = _coerce_v2(_merge(before, patch))
    changed["revision"] = int(before.get("revision") or 1)
    changed["revisions"] = copy.deepcopy(before.get("revisions") or {"audio": 1, "visual": 1})
    changed = validate_settings(changed)
    audio_changed = _canonical(before.get("audio")) != _canonical(changed.get("audio"))
    visual_changed = _canonical(before.get("visual")) != _canonical(changed.get("visual"))
    output_changed = _canonical(before.get("output")) != _canonical(changed.get("output"))
    if audio_changed or visual_changed or output_changed:
        changed["revision"] = int(before.get("revision") or 1) + 1
    if audio_changed or output_changed:
        changed["revisions"]["audio"] = int(before.get("revisions", {}).get("audio") or 1) + 1
    if visual_changed or output_changed:
        changed["revisions"]["visual"] = int(before.get("revisions", {}).get("visual") or 1) + 1
    return _with_aliases(validate_settings(changed))


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a v2 settings object; raises ValueError."""
    if not isinstance(settings, dict):
        raise ValueError("production_settings must be an object")
    out = _coerce_v2(copy.deepcopy(settings))
    out["route_id"] = str(out.get("route_id") or "local_motion")
    if out["route_id"] not in ROUTES:
        raise ValueError(f"unknown route: {out['route_id']}")
    output = out.get("output") if isinstance(out.get("output"), dict) else {}
    if output.get("aspect") not in ASPECTS:
        raise ValueError("aspect must be 9:16, 16:9 or 1:1")
    if output.get("resolution") not in RESOLUTIONS:
        raise ValueError("resolution must be 480p, 720p or 1080p")
    try:
        duration = float(output.get("duration_s") or 0)
    except (TypeError, ValueError):
        duration = 0
    if not 3 <= duration <= 120:
        raise ValueError("duration_s must be between 3 and 120 seconds")
    if int(output.get("fps") or 0) not in FPS:
        raise ValueError("fps must be 24 or 30")

    audio = out.get("audio") if isinstance(out.get("audio"), dict) else {}
    if audio.get("mode") not in AUDIO_MODES:
        raise ValueError("audio.mode must be external_tts, model_native or silent")
    if audio.get("mode") == "external_tts" and audio.get("provider") not in AUDIO_PROVIDERS:
        raise ValueError("audio.provider must be local, minimax, elevenlabs or heygen")
    if audio.get("fit") not in AUDIO_FITS:
        raise ValueError("audio.fit must be trim, pad or stretch")
    try:
        speed = float(audio.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if not 0.5 <= speed <= 2.0:
        raise ValueError("audio.speed must be between 0.5 and 2.0")
    audio["speed"] = speed
    audio["voice_id"] = str(audio.get("voice_id") or "")
    audio["language"] = str(audio.get("language") or "zh-CN")
    audio["generate_before_video"] = bool(audio.get("generate_before_video", audio.get("mode") == "external_tts"))
    out["audio"] = audio

    visual = out.get("visual") if isinstance(out.get("visual"), dict) else {}
    if visual.get("mode") not in MODES:
        raise ValueError("visual.mode must be auto or manual")
    if visual.get("quality_tier") not in TIERS:
        raise ValueError("visual.quality_tier must be draft, standard or premium")
    for key in ("talking_head_profile", "broll_profile", "product_profile"):
        if visual.get(key) is not None:
            visual[key] = str(visual.get(key))
    visual["allow_fallback"] = bool(visual.get("allow_fallback"))
    out["visual"] = visual

    budget = out.get("budget") if isinstance(out.get("budget"), dict) else {}
    for key in ("total_usd", "audio_usd", "video_usd"):
        try:
            budget[key] = float(budget.get(key) or 0)
        except (TypeError, ValueError):
            budget[key] = 0
    if budget["total_usd"] <= 0:
        raise ValueError("budget.total_usd must be greater than 0")
    if budget["audio_usd"] < 0 or budget["video_usd"] < 0:
        raise ValueError("budget components must not be negative")
    out["budget"] = budget
    revisions = out.get("revisions") if isinstance(out.get("revisions"), dict) else {}
    revisions["audio"] = max(1, int(revisions.get("audio") or 1))
    revisions["visual"] = max(1, int(revisions.get("visual") or 1))
    out["revisions"] = revisions
    out["schema_version"] = SCHEMA_VERSION
    out["output"] = output
    return _with_aliases(out)


def summary(settings: dict[str, Any]) -> str:
    output = settings.get("output") or {}
    audio = settings.get("audio") or {}
    visual = settings.get("visual") or {}
    parts = [
        str(output.get("aspect") or "9:16"),
        f"{output.get('duration_s') or 15}s",
        str(output.get("resolution") or "720p"),
        str(settings.get("route_id") or ""),
    ]
    if visual.get("talking_head_profile"):
        parts.append(str(visual["talking_head_profile"]))
    parts.append(str(audio.get("mode") or "silent"))
    return " · ".join(parts)
