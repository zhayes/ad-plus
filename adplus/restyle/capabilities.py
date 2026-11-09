"""Restyle capability audit against the real OpenMontage tool registry.

M-1 exists because Restyle must reuse existing tools and pipelines, not build a
second orchestrator.  This module answers: what is already available, what is
missing, and which provider can actually do ``video_edit`` today?
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR = ROOT / "vendor" / "openmontage"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

WANTED = [
    "scene_detect",
    "video_analyzer",
    "frame_sampler",
    "video_understand",
    "visual_qa",
    "video_stitch",
    "video_compose",
    "video_trimmer",
    "bg_remove",
    "atlas_video",
    "video_selector",
    "runway_video",
    "vidu_video",
    "seedance_video",
    "kling_video",
    "minimax_video",
]


def _status(tool: Any) -> str:
    try:
        return getattr(tool.get_status(), "value", str(tool.get_status()))
    except Exception as exc:  # noqa: BLE001 - an audit must not crash the app
        return f"error:{str(exc)[:80]}"


@lru_cache(maxsize=1)
def audit() -> dict[str, Any]:
    from tools.tool_registry import registry

    registry.ensure_discovered()
    tools: dict[str, Any] = {}
    for name in WANTED:
        tool = registry.get(name)
        if tool is None:
            tools[name] = {"registered": False, "status": "missing"}
            continue
        info = tool.get_info()
        tools[name] = {
            "registered": True,
            "status": _status(tool),
            "capability": info.get("capability"),
            "provider": info.get("provider"),
            "runtime": info.get("runtime"),
            "stability": info.get("stability"),
            "capabilities": info.get("capabilities") or [],
            "dependencies": info.get("dependencies") or [],
        }

    edit_tools = []
    for tool in registry.find_by_capability("video_edit"):
        try:
            edit_tools.append({
                "name": tool.name,
                "provider": tool.provider,
                "status": _status(tool),
                "stability": getattr(tool.stability, "value", str(tool.stability)),
                "capabilities": list(tool.capabilities),
            })
        except Exception as exc:  # noqa: BLE001
            edit_tools.append({"name": getattr(tool, "name", "?"), "error": str(exc)[:120]})

    pipelines = []
    try:
        from lib.pipeline_loader import get_stage_order, list_pipelines, load_pipeline_readonly

        for name in list_pipelines():
            try:
                manifest = load_pipeline_readonly(name)
                pipelines.append({
                    "name": name,
                    "stages": get_stage_order(manifest),
                    "category": manifest.get("category"),
                })
            except Exception as exc:  # noqa: BLE001
                pipelines.append({"name": name, "error": str(exc)[:120]})
    except Exception as exc:  # noqa: BLE001
        pipelines.append({"name": "?", "error": str(exc)[:120]})

    return {
        "vendor": str(VENDOR),
        "tools": tools,
        "video_edit_tools": edit_tools,
        "pipelines": pipelines,
        "gaps": _gaps(tools, edit_tools, pipelines),
    }


def _gaps(tools: dict[str, Any], edit_tools: list[dict[str, Any]], pipelines: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for name in ("scene_detect", "video_analyzer", "video_compose", "video_stitch"):
        if not tools.get(name, {}).get("registered"):
            gaps.append(f"missing tool: {name}")
    if not edit_tools:
        gaps.append("no video_edit provider found; outfit edit needs a new tool/provider")
    elif not any(item.get("status") == "available" for item in edit_tools):
        gaps.append("video_edit providers exist but none available (check API keys / deps)")
    if not tools.get("bg_remove", {}).get("registered"):
        gaps.append("missing bg_remove; no local person mask baseline")
    if not any(item.get("name") == "restyle" for item in pipelines):
        gaps.append("no restyle pipeline manifest; hybrid can be reused or a new manifest added")
    return gaps


def summary() -> dict[str, Any]:
    data = audit()
    return {
        "gaps": data["gaps"],
        "video_edit_tools": data["video_edit_tools"],
        "available": [
            name for name, row in data["tools"].items() if row.get("status") == "available"
        ],
        "unavailable": [
            name for name, row in data["tools"].items() if row.get("status") != "available"
        ],
        "pipelines": [row.get("name") for row in data["pipelines"] if row.get("name")],
    }
