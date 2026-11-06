"""Thin adapter to OpenMontage pipeline manifests.

Ad+ is allowed to own commerce domain data and UI, but it must not invent a
second stage model.  Pipeline names, stage order and canonical artifacts come
from the upstream manifests; this module only maps Ad+ routes onto them.
"""

from __future__ import annotations

import copy
from typing import Any

ROUTE_PIPELINES: dict[str, str] = {
    "local_motion": "animation",
    "hybrid": "hybrid",
    "avatar_spokesperson": "avatar-spokesperson",
}

# Ad+ board stage -> canonical OpenMontage stage.  ``proposal`` is an Ad+
# commercial gate, not a production stage; it is kept mapped for payload
# compatibility but never written as a canonical production artifact.
STAGE_MAP: dict[str, str] = {
    "brief": "idea",
    "proposal": "proposal",
    "script": "script",
    "scene": "scene_plan",
    "assets": "assets",
    "compose": "compose",
    "review": "publish",
}

CANONICAL_ARTIFACTS: dict[str, str] = {
    "idea": "brief",
    "proposal": "proposal_packet",
    "script": "script",
    "scene_plan": "scene_plan",
    "assets": "asset_manifest",
    "edit": "edit_decisions",
    "compose": "render_report",
    "publish": "publish_log",
}


def _loader():
    from lib.pipeline_loader import get_stage_order, load_pipeline_readonly

    return load_pipeline_readonly, get_stage_order


def pipeline_names() -> list[str]:
    from lib.pipeline_loader import list_pipelines

    return list_pipelines()


def pipeline_for_route(route_id: str) -> str:
    return ROUTE_PIPELINES.get(route_id, "animation")


def pipeline_view(name: str) -> dict[str, Any]:
    """Return immutable manifest facts used by Ad+ route/stage projection."""
    try:
        load, order = _loader()
        manifest = load(name)
        stages = order(manifest)
        return {
            "name": name,
            "version": manifest.get("version"),
            "category": manifest.get("category"),
            "description": str(manifest.get("description") or "").strip(),
            "stages": stages,
            "stage_artifacts": {stage: CANONICAL_ARTIFACTS.get(stage) for stage in stages},
            "required_tools": list(manifest.get("required_tools") or []),
            "orchestration": copy.deepcopy(manifest.get("orchestration") or {}),
            "available": True,
            "error": None,
        }
    except Exception as exc:  # manifest missing/invalid must not crash the board
        return {
            "name": name,
            "stages": [],
            "stage_artifacts": {},
            "required_tools": [],
            "available": False,
            "error": str(exc)[:300],
        }


def route_view(route_id: str) -> dict[str, Any]:
    pipeline = pipeline_for_route(route_id)
    view = pipeline_view(pipeline)
    return {
        "route_id": route_id,
        "pipeline": pipeline,
        "stages": view.get("stages") or [],
        "stage_artifacts": view.get("stage_artifacts") or {},
        "required_tools": view.get("required_tools") or [],
        "available": bool(view.get("available")),
        "error": view.get("error"),
    }


def stage_projection() -> dict[str, str]:
    """Ad+ stage -> canonical stage, copied so callers cannot mutate module state."""
    return dict(STAGE_MAP)


def canonical_artifact(stage: str) -> str | None:
    return CANONICAL_ARTIFACTS.get(stage)
