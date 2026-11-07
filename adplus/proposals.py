"""Normalize proposal artifacts into the shape the Ad+ plan page renders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adplus import project_store

PROPOSALS = project_store.PROJECTS


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _workspace_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(project_store.PROJECTS.parent.resolve()).as_posix()
    except ValueError:
        return str(path)


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _brief(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    return {
        "product": str(raw.get("product") or project.get("title") or ""),
        "audience": str(raw.get("audience") or ""),
        "description": str(raw.get("description") or raw.get("selling_points") or ""),
        "tone": str(raw.get("tone") or ""),
        "must_say": str(raw.get("must_say") or ""),
        "avoid": str(raw.get("avoid") or ""),
        "budget_usd": raw.get("budget_usd"),
        "references": _strings(raw.get("references")),
    }


def _concept(packet: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    concept = packet.get("concept") if isinstance(packet.get("concept"), dict) else {}
    options = packet.get("concept_options") if isinstance(packet.get("concept_options"), list) else []
    selected_id = (packet.get("selected_concept") or {}).get("concept_id") if isinstance(packet.get("selected_concept"), dict) else None
    chosen = next((item for item in options if isinstance(item, dict) and item.get("id") == selected_id), None)
    chosen = chosen or (options[0] if options and isinstance(options[0], dict) else {})
    source = {**chosen, **concept}
    rationale = ""
    if isinstance(packet.get("selected_concept"), dict):
        rationale = str(packet["selected_concept"].get("rationale") or "")
    return {
        "title": str(source.get("title") or quote.get("headline") or "未命名方案"),
        "hook": str(source.get("hook") or ""),
        "insight": str(source.get("insight") or source.get("why_this_works") or ""),
        "visual_approach": str(source.get("visual_approach") or source.get("description") or ""),
        "core_message": str(source.get("core_message") or ""),
        "cta": str(source.get("cta") or ""),
        "rationale": rationale,
    }


def _shots(packet: dict[str, Any], scene_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = packet.get("shots") or packet.get("rough_shots") or packet.get("storyboard")
    if not raw and scene_plan:
        raw = scene_plan.get("scenes") or scene_plan.get("shots")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    cursor = 0.0
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        duration = item.get("duration_s")
        try:
            duration = float(duration if duration is not None else item.get("duration") or 2.5)
        except (TypeError, ValueError):
            duration = 2.5
        start = item.get("start_s")
        try:
            start = float(start if start is not None else cursor)
        except (TypeError, ValueError):
            start = cursor
        rows.append({
            "id": str(item.get("id") or f"s{index}"),
            "index": index,
            "role": str(item.get("role") or item.get("narrative_role") or "build"),
            "duration_s": max(0.4, duration),
            "start_s": max(0.0, start),
            "visual": str(item.get("visual") or item.get("description") or item.get("framing") or ""),
            "text": str(item.get("text") or item.get("on_screen_text") or ""),
            "narration": str(item.get("narration") or ""),
            "transition": str(item.get("transition") or item.get("transition_in") or "cut"),
        })
        cursor = start + duration
    return rows


def _deliverables(project: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    raw = packet.get("deliverables") if isinstance(packet.get("deliverables"), dict) else {}
    return {
        "platform": str(raw.get("platform") or project.get("platform") or "douyin"),
        "aspect": str(raw.get("aspect") or project.get("aspect") or "9:16"),
        "duration_s": float(raw.get("duration_s") or project.get("duration_s") or 15),
        "versions": int(raw.get("versions") or 1),
        "captions": bool(raw.get("captions", True)),
        "music": str(raw.get("music") or "按方案配置"),
        "voice": str(raw.get("voice") or "按方案配置"),
        "note": str(raw.get("note") or ""),
    }


def _keyframes(project_id: str, packet: dict[str, Any], quote: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    raw = packet.get("keyframes") if isinstance(packet.get("keyframes"), list) else []
    raw = list(raw) + list(quote.get("shots_preview") or [])
    for item in raw:
        path = item.get("path") if isinstance(item, dict) else item
        if not path:
            continue
        file = Path(str(path))
        if not file.is_absolute():
            file = project_store.PROJECTS.parent / file
        if file.is_file():
            rows.append({"path": _workspace_rel(file), "label": str(item.get("label") or "") if isinstance(item, dict) else ""})
    if rows:
        return rows[:5]
    previews = project_store.PROJECTS / project_id / "previews"
    if previews.is_dir():
        for file in sorted(previews.glob("*.png"))[:3]:
            rows.append({"path": _workspace_rel(file), "label": file.stem})
    return rows


def proposal_payload(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    if project is None:
        return None
    root = project_store.PROJECTS / project_id
    packet = _read(root / "artifacts" / "proposal_packet.json") or {}
    scene_plan = _read(root / "artifacts" / "scene_plan.json")
    quote = project_store.latest_quote(project_id) or {}
    quote_status = str(quote.get("status") or "")
    if quote_status == "approved":
        status = "approved"
    elif quote_status == "rejected":
        status = "rejected"
    elif quote_status == "pending":
        status = "ready"
    elif packet:
        status = "ready"
    else:
        status = "none"
    return {
        "project": project,
        "brief": _brief(project),
        "status": status,
        "concept": _concept(packet, quote),
        "script": _strings(packet.get("script") or packet.get("script_outline")),
        "shots": _shots(packet, scene_plan),
        "deliverables": _deliverables(project, packet),
        "keyframes": _keyframes(project_id, packet, quote),
        "assumptions": list(dict.fromkeys(_strings(quote.get("assumptions")) + _strings(packet.get("assumptions")))),
        "exclusions": _strings(packet.get("exclusions") or packet.get("not_included")),
        "quote": quote or None,
        "generated_at": packet.get("generated_at") or packet.get("created_at"),
        "has_packet": bool(packet),
        "has_quote": bool(quote),
    }
