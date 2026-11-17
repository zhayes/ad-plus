"""Headless proposal generation for the Ad+ plan page.

This intentionally does not reuse the director chat UI: the plan page starts a
short, tool-restricted Pi session that writes a proposal packet and a
non-blocking quote, then exits. The user reviews the result in the plan page.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from adplus import jobs as job_store
from adplus import project_store
from adplus.paths import WORKSPACE
from app import secrets_store
from app.pi_bridge import PiBridge

SESSIONS = secrets_store.app_data_dir() / "proposal-sessions"
TIMEOUT_SECONDS = 240

_active: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class AlreadyRunning(RuntimeError):
    pass


class ProposalError(RuntimeError):
    pass


def _model() -> tuple[str, str]:
    raw = str(__import__("os").environ.get("ADPLUS_PROPOSAL_MODEL") or "deepseek/deepseek-flash")
    provider, _, model = raw.partition("/")
    return provider or "deepseek", model or "deepseek-flash"


def _fallback_packet(project: dict[str, Any], brief: dict[str, Any], feedback: str) -> dict[str, Any]:
    product = str(brief.get("product") or project.get("title") or "产品")
    audience = str(brief.get("audience") or "目标用户")
    tone = str(brief.get("tone") or "直接、有记忆点")
    description = str(brief.get("description") or "")
    duration = float(project.get("duration_s") or 15)
    count = 5 if duration >= 12 else 3
    each = round(duration / count, 2)
    roles = ["hook", "build", "build", "build", "cta"][:count]
    shots = []
    for index, role in enumerate(roles, start=1):
        shots.append({
            "id": f"s{index}",
            "role": role,
            "duration_s": each,
            "visual": f"{product} 的{'开场钩子' if role == 'hook' else ('落版' if role == 'cta' else '核心演示')}，{tone}。",
            "text": f"{product} · {'先看这一眼' if role == 'hook' else ('现在就试' if role == 'cta' else '')}".strip(" ·"),
            "transition": "cut",
        })
    return {
        "concept": {
            "title": f"{product} · {tone}",
            "hook": f"第一秒就让{audience}看到{product}最直接的好处。",
            "insight": description or f"先说清楚{product}对{audience}的价值，再给一个明确的下一步。",
            "visual_approach": f"以{product}为主体，快节奏、强对比，字幕与动作同步；先钩子，再演示，最后落版。",
            "core_message": description or f"{product}，现在就可以试。",
            "cta": f"了解{product}",
        },
        "script": [f"0-{each}s：钩子，直接展示{product}。", f"{each}-{duration - each}s：核心利益点与使用场景。", f"最后 {each}s：品牌与 CTA。"],
        "shots": shots,
        "deliverables": {
            "platform": project.get("platform") or "douyin",
            "aspect": project.get("aspect") or "9:16",
            "duration_s": duration,
            "versions": 1,
            "captions": True,
            "music": "按方案配置",
            "voice": "按方案配置",
        },
        "assumptions": ["使用项目现有品牌信息与默认平台规格。", "关键帧在分镜阶段生成。"],
        "exclusions": ["真人实拍", "额外语言版本"],
        "feedback": feedback,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def _prompt(project: dict[str, Any], brief: dict[str, Any], feedback: str) -> str:
    settings = project.get("production_settings") if isinstance(project.get("production_settings"), dict) else {}
    output = settings.get("output") if isinstance(settings.get("output"), dict) else {}
    duration = float(output.get("duration_s") or project.get("duration_s") or 15)
    aspect = str(output.get("aspect") or project.get("aspect") or "9:16")
    payload = json.dumps(project, ensure_ascii=False, indent=2)
    brief_text = json.dumps(brief, ensure_ascii=False, indent=2)
    settings_text = json.dumps(settings, ensure_ascii=False, indent=2)
    return f"""You are the proposal director for Ad+, a short-form AI ad tool.

Create ONE production-ready proposal for this project. Do not ask questions. Do not render.

PROJECT:
{payload}

BRIEF:
{brief_text}

PRODUCTION SETTINGS (these are user choices, do not silently change them):
{settings_text}

USER FEEDBACK (may be empty):
{feedback or "none"}

Call the OpenMontage MCP tool `om_proposal` exactly once with:
  project_id="{project['id']}"
  headline="<short Chinese headline>"
  brief="<one-line Chinese brief>"
  duration_seconds={duration}
  aspect="{aspect}"
  packet={{
    "concept": {{
      "title": "short Chinese title",
      "hook": "one sentence hook",
      "insight": "why this works for the audience",
      "visual_approach": "how it looks on screen",
      "core_message": "one sentence",
      "cta": "one sentence"
    }},
    "script": ["0-2s: ...", "2-6s: ..."],
    "shots": [
      {{"id":"s1","role":"hook","duration_s":2.2,"visual":"what we see","text":"on-screen text","transition":"cut"}}
    ],
    "deliverables": {{
      "platform":"douyin","aspect":"{aspect}","duration_s":{duration},
      "versions":1,"captions":true,"music":"...","voice":"..."
    }},
    "assumptions": ["..."],
    "exclusions": ["..."]
  }}

Use 3-5 shots and make durations sum to {duration}s. Write Chinese copy.
Call no other tool. Return no prose; the tool is the output."""


def _set_stage(job: dict[str, Any], stage: str, progress: float, **fields: Any) -> None:
    try:
        job_store.update(job, stage=stage, progress=progress, **fields)
    except Exception:
        pass


def _run(project_id: str, job: dict[str, Any], prompt: str) -> None:
    bridge: PiBridge | None = None
    tail: list[str] = []
    try:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        provider, model = _model()
        bridge = PiBridge(
            cwd=WORKSPACE,
            provider=provider,
            model=model,
            session_dir=SESSIONS,
            session_id=f"proposal-{job['id']}",
            extra_args=[
                "--no-builtin-tools",
                "--tools",
                "mcp__openmontage__om_proposal",
            ],
        )
        with _lock:
            if project_id in _active:
                _active[project_id]["bridge"] = bridge
        _set_stage(job, "理解简报", 0.08)
        bridge.prompt(prompt)
        deadline = time.time() + TIMEOUT_SECONDS
        while True:
            if job_store.cancel_requested(project_id, job["id"]):
                try:
                    bridge.abort()
                except Exception:
                    pass
                job_store.finish(job, "cancelled", error="cancelled by user")
                return
            if time.time() > deadline:
                job_store.finish(job, "failed", error="方案生成超时（240s）", output=None)
                return
            try:
                event = bridge.events.get(timeout=1.0)
            except queue.Empty:
                continue
            if event is None:
                break
            kind = event.get("type")
            if kind == "tool_execution_start":
                name = str(event.get("toolName") or "").replace("mcp__openmontage__", "")
                if name == "om_proposal":
                    _set_stage(job, "生成方案", 0.72, log_tail=tail[-40:])
            elif kind == "log":
                raw = str(event.get("raw") or "").strip()
                if raw:
                    tail.append(raw[-500:])
            elif kind in ("agent_end", "agent_settled", "error"):
                if kind == "error":
                    tail.append(str(event.get("message") or event)[:500])
                break

        quote = project_store.latest_quote(project_id)
        if not quote:
            job_store.update(job, log_tail=tail[-40:])
            job_store.finish(job, "failed", error="agent 没有产出报价；请重试或检查模型/Pi 配置")
            return
        if not (project_store.PROJECTS / project_id / "artifacts" / "proposal_packet.json").is_file():
            fallback = _fallback_packet(project_store.load_project(project_id) or {}, {}, "")
            (project_store.PROJECTS / project_id / "artifacts" / "proposal_packet.json").write_text(
                json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tail.append("proposal_packet fallback written")
        _set_stage(job, "完成", 1.0, log_tail=tail[-40:])
        job_store.finish(job, "done", output=str(quote.get("id") or ""))
    except Exception as exc:  # noqa: BLE001 — job state must always settle
        try:
            job_store.finish(job, "failed", error=f"{type(exc).__name__}: {exc}", output=None)
        except Exception:
            pass
    finally:
        if bridge is not None:
            try:
                bridge.close()
            except Exception:
                pass
        with _lock:
            entry = _active.get(project_id)
            if entry and entry.get("job_id") == job.get("id"):
                _active.pop(project_id, None)


def start(project_id: str, brief: dict[str, Any] | None = None, feedback: str = "") -> dict[str, Any]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    with _lock:
        if project_id in _active:
            raise AlreadyRunning(project_id)
        if brief is not None:
            project = project_store.update_project(project_id, {"brief": brief})
        job = job_store.start(
            "proposal", project_id,
            stage="准备", progress=0.02, log_tail=[],
            model="/".join(_model()),
        )
        _active[project_id] = {"job_id": job["id"], "bridge": None, "started": time.time()}
    thread = threading.Thread(
        target=_run,
        args=(project_id, job, _prompt(project, brief or project.get("brief") or {}, feedback)),
        name=f"proposal-{job['id']}",
        daemon=True,
    )
    thread.start()
    return job


def cancel(project_id: str) -> dict[str, Any] | None:
    with _lock:
        entry = _active.get(project_id)
    if entry:
        job = job_store.get(project_id, entry["job_id"])
        if job:
            try:
                job_store.request_cancel(project_id, job["id"])
            except Exception:
                pass
        bridge = entry.get("bridge")
        if bridge is not None:
            try:
                bridge.abort()
            except Exception:
                pass
        return job
    latest = latest_job(project_id)
    if latest and latest.get("status") == "running":
        try:
            return job_store.request_cancel(project_id, latest["id"])
        except Exception:
            return latest
    return latest


def latest_job(project_id: str) -> dict[str, Any] | None:
    try:
        rows = [row for row in job_store.list_jobs(project_id, limit=20) if row.get("kind") == "proposal"]
    except Exception:
        return None
    return rows[0] if rows else None


def status(project_id: str) -> dict[str, Any] | None:
    with _lock:
        entry = _active.get(project_id)
    if entry:
        job = job_store.get(project_id, entry["job_id"]) or {"id": entry["job_id"], "status": "running"}
        job["active"] = True
        return job
    job = latest_job(project_id)
    if job:
        job["active"] = False
    return job
