"""Cost estimates for a whole ad, built from per-tool pricing.

Most paid tools already implement ``estimate_cost()`` / ``estimate_runtime()``
(tools/base_tool.py). A few deliberately refuse to invent a number and raise
``PriceQuoteRequired`` — those become "需询价" line items instead of a made-up
figure, which is the same policy the rest of the repo follows.
"""

from __future__ import annotations

import time
from typing import Any

# Measured on this machine: 450 frames ≈ 6m47s, 600 frames ≈ 23m.
DEFAULT_SECONDS_PER_FRAME = 1.6
LOW_FACTOR = 0.8
HIGH_FACTOR = 1.35

STATUS_ESTIMATED = "estimated"
STATUS_FREE = "free"
STATUS_QUOTE_REQUIRED = "quote_required"
STATUS_UNKNOWN = "unknown"


def _registry() -> Any:
    from tools.tool_registry import registry

    registry.discover()
    return registry


def _is_quote_required(exc: Exception) -> bool:
    return type(exc).__name__ == "PriceQuoteRequired" or "quote" in str(exc).lower()


def _estimate_for(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        tool = _registry().get(tool_name)
    except Exception:
        return {"usd": 0.0, "seconds": 0.0, "status": STATUS_UNKNOWN}
    if tool is None:
        return {"usd": 0.0, "seconds": 0.0, "status": STATUS_UNKNOWN}

    usd: float | None = None
    status = STATUS_UNKNOWN
    try:
        value = tool.estimate_cost(params)
        usd = float(value or 0.0)
        status = STATUS_FREE if usd <= 0 else STATUS_ESTIMATED
    except Exception as exc:  # noqa: BLE001 - a quote must not fail the run
        status = STATUS_QUOTE_REQUIRED if _is_quote_required(exc) else STATUS_UNKNOWN
        usd = None

    seconds = 0.0
    try:
        seconds = float(tool.estimate_runtime(params) or 0.0)
    except Exception:
        seconds = 0.0

    return {"usd": usd or 0.0, "seconds": max(0.0, seconds), "status": status}


def build_quote(
    project_id: str,
    shots: list[dict[str, Any]],
    render: dict[str, Any] | None = None,
    headline: str = "",
) -> dict[str, Any]:
    """Turn a shot list into a quote record ready for :mod:`lib.agent_bridge`.

    ``shots`` items: ``{tool, label?, params?, count?}``.
    ``render`` item: ``{frames?, fps?, seconds_per_frame?}`` — ETA only.
    """
    line_items: list[dict[str, Any]] = []
    total_usd = 0.0
    total_seconds = 0.0
    pending_quotes = 0

    for shot in shots or []:
        tool = str(shot.get("tool") or "").strip()
        if not tool:
            continue
        count = max(1, int(shot.get("count") or 1))
        est = _estimate_for(tool, shot.get("params") or {})
        usd = est["usd"] * count if est["status"] == STATUS_ESTIMATED else 0.0
        seconds = est["seconds"] * count
        if est["status"] == STATUS_QUOTE_REQUIRED:
            pending_quotes += 1
        total_usd += usd
        total_seconds += seconds
        line_items.append(
            {
                "tool": tool,
                "label": str(shot.get("label") or tool),
                "usd": round(usd, 4),
                "unit_usd": round(est["usd"], 4),
                "count": count,
                "seconds": round(seconds, 1),
                "status": est["status"],
            }
        )

    render_seconds = 0.0
    if render:
        frames = int(render.get("frames") or 0)
        per_frame = float(render.get("seconds_per_frame") or DEFAULT_SECONDS_PER_FRAME)
        render_seconds = round(frames * per_frame, 1)
        if render_seconds:
            line_items.append(
                {
                    "tool": "render",
                    "label": f"渲染 {frames} 帧",
                    "usd": 0.0,
                    "unit_usd": 0.0,
                    "count": 1,
                    "seconds": render_seconds,
                    "status": STATUS_FREE,
                }
            )
            total_seconds += render_seconds

    total_usd = round(total_usd, 4)
    paid = [i for i in line_items if i["status"] == STATUS_ESTIMATED and i["usd"] > 0]
    if not headline:
        headline = (
            f"{len(paid)} 个付费项 · 约 {total_seconds / 60:.0f} 分钟" if paid
            else f"本地渲染 · 约 {total_seconds / 60:.0f} 分钟"
        )
    return {
        "project_id": project_id,
        "currency": "USD",
        "headline": headline,
        "total_usd": total_usd,
        "low_usd": round(total_usd * LOW_FACTOR, 4),
        "high_usd": round(total_usd * HIGH_FACTOR, 4),
        "eta_seconds": round(total_seconds, 1),
        "pending_quotes": pending_quotes,
        "line_items": line_items,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def _configured(names: tuple[str, ...]) -> str | None:
    import os


    for name in names:
        if os.environ.get(name):
            return name
    return None


def plan_from_brief(
    brief: str,
    duration_seconds: float = 15,
    aspect: str = "9:16",
    with_voice: bool = False,
    fps: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Derive a shot plan from a one-line brief so turn one can still quote.

    Providers are chosen from what is actually configured; with no keys the
    plan is local-only and priced at the render time alone.
    """
    duration = max(3.0, min(120.0, float(duration_seconds or 15)))
    scenes = max(3, min(8, round(duration / 3.5) + 1))
    per_scene = duration / scenes
    notes: list[str] = [f"{scenes} 个镜头 · 每镜约 {per_scene:.1f}s", f"{aspect} · {fps}fps"]

    video_key = _configured(("ATLASCLOUD_API_KEY", "KLING_API_KEY", "MINIMAX_API_KEY", "FAL_KEY"))
    shots: list[dict[str, Any]] = []
    if video_key == "ATLASCLOUD_API_KEY":
        shots.append({"tool": "atlas_video", "label": f"{scenes} 个镜头 · Atlas Cloud 视频",
                      "params": {"duration": max(4, round(per_scene)), "model_variant": "standard"}, "count": scenes})
        notes.append("画面由 Atlas Cloud 生成")
    elif video_key == "KLING_API_KEY":
        shots.append({"tool": "kling_video", "label": f"{scenes} 个镜头 · Kling 视频",
                      "params": {"duration": max(5, round(per_scene))}, "count": scenes})
        notes.append("画面由 Kling 生成")
    elif video_key == "FAL_KEY":
        shots.append({"tool": "flux3_fal_image", "label": f"{scenes} 张场景图 · fal",
                      "params": {"prompt": brief or "ad scene"}, "count": scenes})
        notes.append("画面由 fal 生成（图生视频/动效）")
    else:
        notes.append("未配置图像/视频 key，按本地动效出价")

    if with_voice or _configured(("ELEVENLABS_API_KEY", "AZURE_SPEECH_KEY", "OPENAI_API_KEY")):
        shots.append({"tool": "elevenlabs_tts", "label": f"配音 · 约 {int(duration * 3.2)} 字",
                      "params": {"text": "x" * max(20, int(duration * 3.2))}, "count": 1})
        notes.append("含中文配音")

    render = {"frames": int(duration * max(24, min(60, fps))), "fps": fps}
    return shots, render, notes


def describe(quote: dict[str, Any]) -> str:
    """One-line human summary (used by tool responses and logs)."""
    minutes = quote.get("eta_seconds", 0) / 60
    text = (
        f"${quote.get('low_usd', 0):.2f}–${quote.get('high_usd', 0):.2f}"
        f" · {minutes:.1f} 分钟 · {len(quote.get('line_items') or [])} 项"
    )
    if quote.get("pending_quotes"):
        text += f"（{quote['pending_quotes']} 项需询价）"
    return text
