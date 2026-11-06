"""Ad+ production board state, derived from OpenMontage-style artifacts.

The board is a view over project files. It deliberately keeps the canonical
artifacts (proposal_packet, script, scene_plan, asset manifest, render, review)
as the source of truth and only stores Ad+-specific decisions (route + stage
approvals) alongside them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from adplus import project_store
from adplus import capabilities as model_caps
from adplus import pipeline_adapter

PROJECTS = project_store.PROJECTS

ROUTES: dict[str, dict[str, Any]] = {
    "local_motion": {
        "id": "local_motion",
        "label": "本地动效",
        "pipeline": "animation",
        "runtime": "remotion",
        "description": "程序化动效、文字排版、产品卖点；deterministic、品牌安全。",
        "best_for": "信息型广告 / 产品卖点 / 文字与图形",
        "cost_hint": "$0–0.20",
        "eta_hint": "10–15 分钟",
        "requires": [],
        "available": True,
    },
    "avatar_spokesperson": {
        "id": "avatar_spokesperson",
        "label": "数字人口播",
        "pipeline": "avatar-spokesperson",
        "runtime": "avatar",
        "description": "数字模特 + 音频/脚本，走 Kling Avatar / HeyGen / Wav2Lip；人物与口型独立于商品镜头。",
        "best_for": "主播口播 / 知识带货 / 不需要真人出镜",
        "cost_hint": "$0.30–3.00",
        "eta_hint": "5–15 分钟",
        "requires": ["数字模特授权", "口型/数字人模型 key"],
        "available": False,
    },
    "hybrid": {
        "id": "hybrid",
        "label": "混合实拍",
        "pipeline": "hybrid",
        "runtime": "remotion",
        "description": "真实素材/现有素材为主，生成补镜与设计动效补足。",
        "best_for": "生活方式 / 场景 / 真人感",
        "cost_hint": "$0.40–1.50",
        "eta_hint": "20–40 分钟",
        "requires": ["图片/视频生成 key 或现成素材"],
        "available": False,
    },
}

STAGES: list[dict[str, str]] = [
    {"id": "brief", "label": "简报 / 路线", "short": "简报", "icon": "file-text"},
    {"id": "proposal", "label": "方案", "short": "方案", "icon": "lightbulb"},
    {"id": "script", "label": "脚本", "short": "脚本", "icon": "script"},
    {"id": "scene", "label": "分镜", "short": "分镜", "icon": "layout"},
    {"id": "assets", "label": "素材", "short": "素材", "icon": "image"},
    {"id": "compose", "label": "成片", "short": "成片", "icon": "film"},
    {"id": "review", "label": "审片 / 交付", "short": "审片", "icon": "check"},
]

STAGE_IDS = [item["id"] for item in STAGES]
APPROVED = {"brief", "script", "scene", "assets", "compose"}


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def approvals_path(project_id: str) -> Path:
    return PROJECTS / project_id / "production" / "approvals.json"


def load_approvals(project_id: str) -> dict[str, Any]:
    return _read(approvals_path(project_id)) or {}


def route_catalog() -> list[dict[str, Any]]:
    """Routes are still Ad+ labels, but availability comes from capabilities."""
    profiles = model_caps.list_profiles()
    video_ready = any(item.get("status") == "available" and item.get("capability") == "video_generation" for item in profiles)
    avatar_ready = any(item.get("status") == "available" and item.get("capability") in {"avatar", "lip_sync"} for item in profiles)
    rows: list[dict[str, Any]] = []
    for raw in ROUTES.values():
        item = dict(raw)
        if item["id"] == "hybrid":
            item["available"] = video_ready
        elif item["id"] == "avatar_spokesperson":
            item["available"] = avatar_ready
        item["canonical"] = pipeline_adapter.route_view(str(item["id"]))
        rows.append(item)
    return rows


def route_for(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("route")
    route_id = raw.get("id") if isinstance(raw, dict) else str(raw or "")
    if not route_id:
        pipeline = str(project.get("pipeline_type") or "")
        route_id = "hybrid" if pipeline == "hybrid" else "local_motion"
    route = dict(ROUTES.get(route_id) or ROUTES["local_motion"])
    if isinstance(raw, dict):
        route.update({key: value for key, value in raw.items() if key in ("pipeline", "runtime")})
    return route


def brief_for(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    return {
        "product": str(raw.get("product") or project.get("title") or ""),
        "audience": str(raw.get("audience") or ""),
        "description": str(raw.get("description") or ""),
        "tone": str(raw.get("tone") or ""),
        "must_say": str(raw.get("must_say") or ""),
        "avoid": str(raw.get("avoid") or ""),
        "budget_usd": raw.get("budget_usd"),
        "references": raw.get("references") if isinstance(raw.get("references"), list) else [],
    }


def script_for(project_id: str) -> dict[str, Any] | None:
    root = PROJECTS / project_id
    stored = _read(root / "artifacts" / "script.json")
    if stored and isinstance(stored.get("lines"), list):
        return stored
    if stored and isinstance(stored.get("sections"), list):
        return {
            "source": "canonical",
            "lines": [
                {"id": str(section.get("id") or f"l{index}"), "text": str(section.get("text") or "")}
                for index, section in enumerate(stored["sections"], 1)
                if str(section.get("text") or "").strip()
            ],
        }
    packet = _read(root / "artifacts" / "proposal_packet.json") or {}
    lines = packet.get("script")
    if isinstance(lines, str):
        lines = [line.strip() for line in lines.splitlines() if line.strip()]
    if isinstance(lines, list) and lines:
        return {"source": "proposal", "lines": [{"id": f"l{index}", "text": str(text)} for index, text in enumerate(lines, 1)]}
    return None


def _version(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    if project is None:
        return None
    if project.get("current_version_id"):
        version = project_store.load_version(project_id, str(project["current_version_id"]))
        if version:
            return version
    version = project_store.ensure_version(project_id)
    if version:
        return version
    # Ad+ plan flow: bootstrap a first version from the proposal's rough shots.
    from adplus import proposals

    packet = _read(PROJECTS / project_id / "artifacts" / "proposal_packet.json") or {}
    scene = _read(PROJECTS / project_id / "artifacts" / "scene_plan.json")
    rough = proposals._shots(packet, scene)  # noqa: SLF001 - shared normalizer
    if not rough:
        return None
    version = project_store.create_version(project_id)
    version["shots"] = [
        {
            "id": shot["id"],
            "role": shot["role"],
            "description": shot["visual"],
            "framing": "",
            "movement": "",
            "transition_in": shot["transition"],
            "transition_out": "",
            "on_screen_text": shot["text"],
            "narration": shot["narration"],
            "status": "planned",
            "locked": False,
            "preview": None,
            "take_count": 0,
            "cost_usd": 0,
            "duration_s": shot["duration_s"],
        }
        for shot in rough
    ]
    return project_store.save_version(version)


def _review(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    version = _version(project_id)
    if project is None or version is None:
        return None
    return project_store.latest_review(project_id, str(version.get("id"))) or _read(PROJECTS / project_id / "reviews" / f"{version.get('id')}.json")


def _stage_base(stage_id: str, status: str, *, summary: str, action: str, artifact: str = "") -> dict[str, Any]:
    meta = next((item for item in STAGES if item["id"] == stage_id), {"id": stage_id, "label": stage_id, "short": stage_id})
    return {
        "id": stage_id,
        "label": meta["label"],
        "short": meta.get("short", meta["label"]),
        "icon": meta.get("icon", "circle"),
        "status": status,
        "summary": summary,
        "action": action,
        "artifact": artifact,
    }


def production_payload(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    if project is None:
        return None
    version = _version(project_id)
    shots = (version or {}).get("shots") or []
    render = (version or {}).get("render") or {}
    quote = project_store.latest_quote(project_id)
    proposal = _read(PROJECTS / project_id / "artifacts" / "proposal_packet.json")
    script = script_for(project_id)
    final = _read(PROJECTS / project_id / "artifacts" / "final_review.json")
    review = _review(project_id)
    approvals = load_approvals(project_id)
    route = route_for(project)
    brief = brief_for(project)

    preview_count = sum(1 for shot in shots if shot.get("preview"))
    proposal_ready = bool(proposal or quote)
    quote_status = str((quote or {}).get("status") or "")
    legacy = bool(render.get("path")) and not any(
        key in approvals for key in ("brief", "script", "scene", "assets", "compose")
    )
    review_approved = bool(
        (review or {}).get("status") == "approved"
        or project.get("status") == "delivered"
        or (legacy and (final or {}).get("status") == "pass")
    )

    stage_rows: list[dict[str, Any]] = []

    brief_done = bool(brief.get("product")) and bool(route.get("id")) and (bool(approvals.get("brief")) or legacy)
    stage_rows.append(_stage_base(
        "brief",
        "approved" if brief_done else ("review" if brief.get("product") and route.get("id") else "ready"),
        summary=f"{route.get('label')} · {brief.get('product') or '未填写产品'}",
        action="确认简报与路线" if not brief_done else "已完成",
        artifact="brief + route",
    ))

    if quote_status == "approved" or legacy:
        proposal_status = "approved"
    elif proposal_ready:
        proposal_status = "review"
    else:
        proposal_status = "ready"
    stage_rows.append(_stage_base(
        "proposal",
        proposal_status,
        summary=(quote or {}).get("headline") or ("方案待确认" if proposal_ready else "还没有方案"),
        action="确认方案" if proposal_status == "review" else ("已完成" if proposal_status == "approved" else "生成方案"),
        artifact="proposal_packet + quote",
    ))

    if (approvals.get("script") and script) or legacy:
        script_status = "approved"
    elif script:
        script_status = "review"
    else:
        script_status = "ready"
    stage_rows.append(_stage_base(
        "script",
        script_status,
        summary=f"{len(script.get('lines', []))} 段文案" if script else "还没有脚本",
        action="确认脚本" if script_status == "review" else ("已完成" if script_status == "approved" else "写脚本"),
        artifact="script",
    ))

    if (approvals.get("scene") and shots) or (legacy and shots):
        scene_status = "approved"
    elif shots:
        scene_status = "review"
    else:
        scene_status = "ready"
    stage_rows.append(_stage_base(
        "scene",
        scene_status,
        summary=f"{len(shots)} 镜 · {float((version or {}).get('duration_s') or 0):.1f}s" if shots else "还没有分镜",
        action="确认分镜" if scene_status == "review" else ("已完成" if scene_status == "approved" else "排分镜"),
        artifact="scene_plan / version.shots",
    ))

    assets_done = (bool(approvals.get("assets")) and bool(shots)) or legacy
    if assets_done:
        assets_status = "approved"
    elif shots:
        assets_status = "review"
    else:
        assets_status = "ready"
    stage_rows.append(_stage_base(
        "assets",
        assets_status,
        summary=f"{preview_count}/{len(shots)} 镜有素材" if shots else "还没有镜头素材",
        action="确认素材" if assets_status == "review" else ("已完成" if assets_status == "approved" else "准备素材"),
        artifact="asset_manifest / shot previews",
    ))

    compose_done = (bool(approvals.get("compose")) and bool(render.get("path"))) or legacy
    if compose_done:
        compose_status = "approved"
    elif render.get("path"):
        compose_status = "review"
    else:
        compose_status = "ready"
    stage_rows.append(_stage_base(
        "compose",
        compose_status,
        summary=Path(str(render.get("path"))).name if render.get("path") else "还没有成片",
        action="确认成片" if compose_status == "review" else ("已完成" if compose_status == "approved" else "渲染成片"),
        artifact="render",
    ))

    if review_approved:
        review_status = "approved"
    elif render.get("path"):
        review_status = "review"
    else:
        review_status = "ready"
    stage_rows.append(_stage_base(
        "review",
        review_status,
        summary="已通过，可以交付" if review_approved else ("待审片" if render.get("path") else "还没有可审成片"),
        action="导出交付" if review_approved else ("审片" if render.get("path") else "等待成片"),
        artifact="final_review",
    ))

    checkpoint_status: dict[str, Any] = {}
    checkpoint_by_stage: dict[str, dict[str, Any]] = {}
    for row in stage_rows:
        row["canonical_stage"] = pipeline_adapter.STAGE_MAP.get(str(row["id"]))
        row["canonical_artifact"] = pipeline_adapter.canonical_artifact(str(row.get("canonical_stage") or ""))
        canonical_stage = row.get("canonical_stage")
        if canonical_stage:
            try:
                from lib.checkpoint import read_checkpoint
                cp = read_checkpoint(PROJECTS, project_id, str(canonical_stage))
            except Exception:
                cp = None
            if cp:
                checkpoint_status[str(canonical_stage)] = cp.get("status")
                checkpoint_by_stage[str(canonical_stage)] = cp
                row["checkpoint_status"] = cp.get("status")
                if cp.get("status") == "completed":
                    row["status"] = "approved"
                    row["action"] = "已完成"
                elif cp.get("status") == "awaiting_human":
                    row["status"] = "review"
                elif cp.get("status") in {"failed", "in_progress"}:
                    row["status"] = "review"
                    row["summary"] = str(cp.get("error") or row.get("summary") or "")
                    row["action"] = "修复后重试"

    if checkpoint_by_stage:
        proposal_row = next((row for row in stage_rows if row["id"] == "proposal"), None)
        if proposal_row is not None:
            # proposal is the Ad+ commercial gate, not a production stage; it
            # must not block canonical pipeline progression.
            proposal_row["status"] = "approved"
            proposal_row["action"] = "商业层独立"
        canonical_stages = list((pipeline_adapter.route_view(str(route.get("id"))).get("stages") or []))
        for row in stage_rows:
            canonical = row.get("canonical_stage")
            if row["id"] == "proposal" or not canonical or canonical in checkpoint_by_stage:
                continue
            # A checkpoint pipeline exists: absence of this checkpoint means
            # the stage has not run, regardless of legacy Ad+ artifacts.
            try:
                position = canonical_stages.index(str(canonical))
            except ValueError:
                continue
            predecessors = canonical_stages[:position]
            ready = all(
                (checkpoint_by_stage.get(stage) or {}).get("status") == "completed"
                for stage in predecessors
            )
            row["status"] = "ready" if ready else "locked"
            row["summary"] = "等待 OpenMontage checkpoint"
            row["action"] = "运行该 stage" if ready else "先完成上一阶段"

    current = next((row for row in stage_rows if row["status"] != "approved"), stage_rows[-1])
    for row in stage_rows:
        index = STAGE_IDS.index(row["id"])
        current_index = STAGE_IDS.index(current["id"])
        if index > current_index and row["status"] != "approved":
            row["status"] = "locked"
            row["action"] = "先完成上一阶段"
    current = next((row for row in stage_rows if row["status"] != "approved"), stage_rows[-1])

    budget = 2.0
    try:
        from app import config_store
        budget = float(config_store.load().get("daily_budget_usd", 2.0))
    except Exception:
        budget = 2.0
    spent = sum(float(item.get("cost_usd") or 0) for item in project_store.list_versions(project_id))

    return {
        "project": project,
        "route": route,
        "routes": route_catalog(),
        "pipeline": pipeline_adapter.route_view(str(route.get("id"))),
        "stage_projection": pipeline_adapter.stage_projection(),
        "checkpoints": checkpoint_status,
        "pipeline_mode": bool(checkpoint_by_stage),
        "models": model_caps.list_profiles(),
        "persona": project_store.persona_snapshot(project.get("persona_id")),
        "product": project_store.product_snapshot(project.get("product_id")),
        "brief": brief,
        "stages": stage_rows,
        "current_stage": current["id"],
        "next_action": current["action"],
        "budget_usd": budget,
        "spent_usd": spent,
        "quote": quote,
        "proposal": proposal,
        "script": script,
        "version": project_store.version_summary(version) if version else None,
        "shots": shots,
        "preview_count": preview_count,
        "render": render or None,
        "review": review,
        "final_review": final,
        "approvals": approvals,
    }


def save_route(project_id: str, route_id: str) -> dict[str, Any]:
    if route_id not in ROUTES:
        raise ValueError(f"unknown route {route_id!r}")
    if not ROUTES[route_id].get("available"):
        raise ValueError("该路线需要额外的素材/生成能力")
    route = dict(ROUTES[route_id])
    return project_store.update_project(
        project_id,
        {"route": route, "status": "briefing", "pipeline_type": route.get("pipeline") or "animation"},
    )


def save_script(project_id: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    project_store.load_project(project_id) or (_ for _ in ()).throw(FileNotFoundError(project_id))
    clean = []
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        clean.append({
            "id": str(line.get("id") or f"l{index}"),
            "text": text,
            "kind": str(line.get("kind") or "voiceover"),
        })
    record = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "lines": clean}
    _write(PROJECTS / project_id / "artifacts" / "script.json", record)
    return record


def approve(project_id: str, stage: str, comment: str = "") -> dict[str, Any]:
    if stage not in APPROVED:
        raise ValueError(f"stage {stage!r} cannot be approved here")
    payload = production_payload(project_id)
    if payload is None:
        raise FileNotFoundError(project_id)
    order = STAGE_IDS.index(stage)
    for previous in STAGE_IDS[:order]:
        row = next((item for item in payload["stages"] if item["id"] == previous), None)
        if row and row["status"] != "approved":
            raise ValueError(f"先完成「{row['label']}」")
    if stage == "brief":
        if not payload["brief"].get("product") or not payload["route"].get("id"):
            raise ValueError("先填写产品并选择制作路线")
    if stage == "script" and not (payload.get("script") or {}).get("lines"):
        raise ValueError("还没有脚本")
    if stage in ("scene", "assets") and not payload.get("shots"):
        raise ValueError("还没有分镜")
    if stage == "compose" and not (payload.get("render") or {}).get("path"):
        raise ValueError("还没有可确认的成片")
    approvals = load_approvals(project_id)
    approvals[stage] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "comment": comment}
    _write(approvals_path(project_id), approvals)
    status = {
        "brief": "briefing",
        "script": "storyboard",
        "scene": "storyboard",
        "assets": "producing",
        "compose": "review",
    }.get(stage)
    if status:
        project_store.update_project(project_id, {"status": status})
    return production_payload(project_id) or {}
