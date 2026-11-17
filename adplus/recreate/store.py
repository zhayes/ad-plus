"""Persisted state for a 「复制爆款」 project.

A recreate is a normal Ad+ project with ``format_id="recreate"`` plus a
``recreate/`` sidecar, exactly like restyle.  That buys jobs, media serving,
trash and project listing for free; this module only owns the step machine and
the artifact files.

Step order is enforced (analyze → gag → script → board → shots → finish) and
each step runs in a worker thread that reports through :mod:`adplus.jobs`.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from adplus import jobs, project_store
from adplus.paths import PROJECTS, WORKSPACE
from adplus.recreate import board as board_mod
from adplus.recreate import extract, gag as gag_mod
from adplus.recreate import script as script_mod
from adplus.recreate import assemble as assemble_mod
from adplus.recreate import qa as qa_mod
from adplus.recreate import render_native
from adplus.recreate import render_cli

FORMAT_ID = "recreate"
STEPS = ["analyze", "gag", "script", "board", "shots", "finish"]
STEP_LABELS = {
    "analyze": "拆解参考片",
    "gag": "抽梗",
    "script": "改编脚本",
    "board": "分镜板",
    "shots": "逐镜出片",
    "finish": "装配与 QA",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _root(project_id: str) -> Path:
    return PROJECTS / project_id / "recreate"


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


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


def _resolve(path: str) -> Path:
    raw = Path(path)
    candidate = raw if raw.is_absolute() else (WORKSPACE / raw)
    if not candidate.is_file():
        raise FileNotFoundError(path)
    return candidate.resolve()


def create(path: str, title: str | None = None, rights_confirmed: bool = False) -> dict[str, Any]:
    source = _resolve(path)
    if not rights_confirmed:
        raise ValueError("rights_confirmed_required")
    facts = extract.media.probe(source)
    project_title = (title or source.stem or "复制爆款").strip()[:80]
    project = project_store.create_project(
        project_title,
        format_id=FORMAT_ID,
        pipeline_type="hybrid",
        aspect=facts.get("aspect") or "9:16",
        duration_s=max(0.5, float(facts.get("duration_s") or 0)),
        platform="douyin",
        route={"id": "hybrid", "pipeline": "hybrid", "runtime": "recreate"},
    )
    project_id = str(project["project_id"])
    root = _root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    stored = root / f"source{source.suffix.lower()}"
    shutil.copy2(source, stored)
    _write(
        root / "source.json",
        {
            "path": _rel(stored),
            "original_path": _rel(source),
            "probe": facts,
            "rights": {"confirmed": True, "confirmed_at": _now()},
            "created_at": _now(),
        },
    )
    _write(root / "steps.json", {"steps": {step: {"status": "pending"} for step in STEPS}})
    return detail(project_id) or {}


def list_recreates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not PROJECTS.is_dir():
        return rows
    for child in sorted(PROJECTS.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or not (child / "recreate").is_dir():
            continue
        row = detail(child.name)
        if row:
            rows.append(
                {
                    "project_id": child.name,
                    "title": (row.get("project") or {}).get("title"),
                    "created_at": (row.get("source") or {}).get("created_at"),
                    "steps": row.get("steps"),
                    "next_step": row.get("next_step"),
                    "duration_s": ((row.get("source") or {}).get("probe") or {}).get("duration_s"),
                }
            )
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows


def detail(project_id: str) -> dict[str, Any] | None:
    project = project_store.load_project(project_id)
    if project is None:
        return None
    root = _root(project_id)
    if not root.is_dir():
        return None
    steps = (_read(root / "steps.json") or {}).get("steps") or {}
    skeleton = _read(root / "p0" / "skeleton.json")
    spec = _read(root / "p1" / "gag_spec.json")
    script = _read(root / "p1" / "script.json")
    board = _read(root / "p2" / "board.json")
    shots = _read(root / "p3" / "shots.json")
    qa = _read(root / "p3" / "qa.json")
    product = _read(root / "product.json")

    return {
        "project": {"project_id": project_id, "title": project.get("title")},
        "source": _read(root / "source.json"),
        "steps": steps,
        "next_step": _next_step(steps),
        "skeleton": skeleton,
        "gag": spec,
        "script": script,
        "board": _board_summary(board),
        "shots": _shots_summary(shots),
        "qa": qa,
        "product": product,
        "files": {
            "final": _rel(root / "p3" / "final.mp4") if (root / "p3" / "final.mp4").is_file() else None,
            "skeleton": _rel(root / "p0" / "skeleton.json"),
        },
    }


def _next_step(steps: dict[str, Any]) -> str | None:
    for step in STEPS:
        status = (steps.get(step) or {}).get("status")
        if status not in {"done", "running"}:
            return step
    return None


def _board_summary(board: dict[str, Any] | None) -> dict[str, Any] | None:
    if not board:
        return None
    return {
        "cast": board.get("cast"),
        "items": [
            {"beat": item.get("beat"), "chosen": item.get("chosen"), "status": item.get("status")}
            for item in board.get("items") or []
        ],
        "cost_estimate_usd": board.get("cost_estimate_usd"),
    }


def _shots_summary(shots: dict[str, Any] | None) -> dict[str, Any] | None:
    if not shots:
        return None
    return {
        "mode": shots.get("mode"),
        "shots": [
            {"beat": key, "mode": value.get("mode"), "status": value.get("status"), "clip": value.get("clip"), "image": value.get("image")}
            for key, value in (shots.get("shots") or {}).items()
        ],
    }


def start_step(project_id: str, step: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if step not in STEPS:
        raise ValueError(f"unknown step {step}")
    if project_store.load_project(project_id) is None or not _root(project_id).is_dir():
        raise FileNotFoundError(project_id)
    params = params or {}
    state = _read(_root(project_id) / "steps.json") or {"steps": {}}
    steps = state.setdefault("steps", {})
    steps[step] = {"status": "running", "started_at": _now()}
    _write(_root(project_id) / "steps.json", state)

    job = jobs.start(f"recreate_{step}", project_id, frames_total=1)

    def run() -> None:
        try:
            _run_step(project_id, step, params, job)
            steps[step] = {"status": "done", "finished_at": _now()}
            _write(_root(project_id) / "steps.json", {"steps": steps})
            jobs.finish(job, "done", output=f"recreate/{step}")
        except Exception as exc:  # noqa: BLE001 - a failed step must stay inspectable
            steps[step] = {"status": "failed", "finished_at": _now(), "error": str(exc)[:400]}
            _write(_root(project_id) / "steps.json", {"steps": steps})
            jobs.finish(job, "failed", error=str(exc)[:500])

    threading.Thread(target=run, name=f"recreate-{step}-{project_id}", daemon=True).start()
    return job


def _run_step(project_id: str, step: str, params: dict[str, Any], job: dict[str, Any]) -> None:
    root = _root(project_id)
    source = _read(root / "source.json") or {}
    video = WORKSPACE / str(source.get("path") or "")
    if not video.is_file():
        raise RuntimeError("source video missing")

    if step == "analyze":
        jobs.update(job, progress=0.05)
        skeleton = extract.analyze(
            video,
            out_dir=root / "p0",
            asr_model=params.get("asr_model"),
            language=params.get("language"),
            max_frames=int(params.get("max_frames") or 8),
            with_vision=bool(params.get("vision", True)),
            with_ocr=bool(params.get("ocr", True)),
        )
        jobs.update(job, progress=1.0)
        if not skeleton.get("beats"):
            raise RuntimeError("没有识别出 beat")
        return

    skeleton = _read(root / "p0" / "skeleton.json")
    if not skeleton:
        raise RuntimeError("先跑拆解")

    if step == "gag":
        spec = gag_mod.extract(skeleton, model=params.get("model"))
        _write(root / "p1" / "gag_spec.json", spec)
        jobs.update(job, progress=1.0)
        return

    if step == "script":
        spec = _read(root / "p1" / "gag_spec.json") or {}
        product = params.get("product") or {}
        if not product.get("name"):
            raise ValueError("缺少商品名")
        _write(root / "product.json", product)
        result = script_mod.adapt(skeleton, spec, product, model=params.get("model"))
        _write(root / "p1" / "script.json", result)
        jobs.update(job, progress=1.0)
        return

    if step == "board":
        script = _read(root / "p1" / "script.json")
        product = _read(root / "product.json") or {}
        mode = str(params.get("mode") or "auto")
        cast = params.get("cast")
        if mode == "cast_only":
            if not cast:
                raise ValueError("cast_only 需要提供 cast 图片路径")
            images = [{"beat": beat["id"], "chosen": cast, "images": [cast], "status": "cast_only"} for beat in skeleton.get("beats") or []]
            _write(root / "p2" / "board.json", {"version": 1, "cast": cast, "items": images, "cost_estimate_usd": 0})
            jobs.update(job, progress=1.0)
            return
        board = board_mod.build_board(skeleton, script, product, root / "p2", cast_path=cast, per_beat=int(params.get("per_beat") or 1))
        if not any(item.get("chosen") for item in board.get("items") or []):
            raise RuntimeError("分镜板一张都没生成（检查额度或 key）")
        jobs.update(job, progress=1.0)
        return

    if step == "shots":
        board = _read(root / "p2" / "board.json")
        if not board:
            raise RuntimeError("先出分镜板")
        script = _read(root / "p1" / "script.json")
        mode = str(params.get("mode") or "video")
        provider = str(params.get("provider") or "auto")
        only = params.get("beats") or None

        doc: dict[str, Any] | None = None
        if mode == "still":
            doc = render_cli.render(skeleton, board, script, root / "p3", mode="still", only=only)
        elif provider == "seedance":
            from adplus.recreate import render_seedance

            doc = render_seedance.render_seedance(
                skeleton, script, root / "p3", reference=params.get("reference") or None, only=only
            )
        else:
            # auto / minimax: try the fast 2K provider first, then fall back to
            # Seedance (independent quota), then to stills so the step never
            # dies silently.
            try:
                doc = render_cli.render(skeleton, board, script, root / "p3", mode="video", only=only)
                if not any(row.get("clip") for row in (doc.get("shots") or {}).values()):
                    raise RuntimeError("minimax 没有产出任何镜头")
            except Exception:
                from adplus.recreate import render_seedance

                try:
                    doc = render_seedance.render_seedance(skeleton, script, root / "p3", only=only)
                except Exception:
                    doc = render_cli.render(skeleton, board, script, root / "p3", mode="still", only=only)
        jobs.update(job, progress=1.0)
        if not doc.get("shots"):
            raise RuntimeError("没有生成任何镜头")
        return

    if step == "finish":
        script = _read(root / "p1" / "script.json")
        shots = _read(root / "p3" / "shots.json")
        if not script or not shots:
            raise RuntimeError("先出脚本和镜头")
        plan = assemble_mod.assemble(
            skeleton, script, shots.get("shots") or {}, root / "p3",
            voice=bool(params.get("voice", True)),
            audio_mode=str(params.get("audio_mode") or "tts"),
        )
        report = qa_mod.check(plan["output"], skeleton, script, timeline=plan)
        _write(root / "p3" / "qa.json", report)
        jobs.update(job, progress=1.0)
        return

    raise ValueError(f"unknown step {step}")


def delete(project_id: str) -> str:
    if project_store.load_project(project_id) is None:
        raise FileNotFoundError(project_id)
    return project_store.trash_project(project_id)


# ---------------------------------------------------------------------------
# One-take pipeline: the UI calls this once and gets a film.
# ---------------------------------------------------------------------------

# Native-audio models speak at a natural pace; lines budgeted at reference speed
# get cut off, so the script is rewritten with this cap when native audio is on.
NATIVE_CPS = 3.9


def start_onetake(project_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run analyze→finish as one job. No per-step user confirmation."""
    if project_store.load_project(project_id) is None or not _root(project_id).is_dir():
        raise FileNotFoundError(project_id)
    params = params or {}
    job = jobs.start("recreate_onetake", project_id, frames_total=1)
    state = {"steps": {step: {"status": "pending"} for step in STEPS}}
    _write(_root(project_id) / "steps.json", state)

    def run() -> None:
        try:
            _run_onetake(project_id, params, job, state)
            for step in STEPS:
                state["steps"][step] = {**state["steps"].get(step, {}), "status": "done", "finished_at": _now()}
            _write(_root(project_id) / "steps.json", state)
            jobs.finish(job, "done", output="recreate/onetake")
        except Exception as exc:  # noqa: BLE001 - the job must stay inspectable
            _write(_root(project_id) / "steps.json", state)
            jobs.finish(job, "failed", error=f"{type(exc).__name__}: {exc}"[:400])

    threading.Thread(target=run, name=f"recreate-onetake-{project_id}", daemon=True).start()
    return job


def _run_onetake(project_id: str, params: dict[str, Any], job: dict[str, Any], state: dict[str, Any]) -> None:
    root = _root(project_id)
    source = _read(root / "source.json") or {}
    video = WORKSPACE / str(source.get("path") or "")
    if not video.is_file():
        raise RuntimeError("source video missing")
    preset = params.get("preset") or {}
    product = params.get("product") or {}
    native = bool(preset.get("native_audio", True))
    resolution = str(preset.get("resolution") or "480p")
    fidelity = str(preset.get("fidelity") or "effect")
    seconds_override = preset.get("duration")

    def mark(step: str, status: str, error: str | None = None) -> None:
        state["steps"][step] = {"status": status, "finished_at": _now() if status != "running" else None}
        if error:
            state["steps"][step]["error"] = error
        _write(root / "steps.json", state)

    def attempt(step: str, fn, *, progress: float):
        mark(step, "running")
        jobs.update(job, progress=progress)
        try:
            return fn()
        except Exception as first:  # noqa: BLE001 - one retry, then degrade
            try:
                return fn()
            except Exception as second:  # noqa: BLE001
                mark(step, "failed", f"{type(second).__name__}: {second}"[:300])
                raise RuntimeError(f"{step} failed after retry: {first!r} / {second!r}") from second

    skeleton = attempt(
        "analyze",
        lambda: extract.analyze(video, out_dir=root / "p0", max_frames=int(preset.get("max_frames") or 6)),
        progress=0.1,
    )
    mark("analyze", "done")
    spec = attempt("gag", lambda: gag_mod.extract(skeleton), progress=0.2)
    _write(root / "p1" / "gag_spec.json", spec)
    mark("gag", "done")

    if not product.get("name"):
        product = {"name": "商品", "price": "39.9", "promo_price": "19.9"}
    _write(root / "product.json", product)
    script = attempt(
        "script",
        lambda: script_mod.adapt(skeleton, spec, product, cps_cap=NATIVE_CPS if native else None),
        progress=0.3,
    )
    _write(root / "p1" / "script.json", script)
    mark("script", "done")

    def _board() -> dict[str, Any]:
        cast = board_mod.build_cast(product, root / "p2", count=1)
        product["cast"] = cast
        _write(root / "product.json", product)
        return board_mod.build_board(skeleton, script, product, root / "p2", cast_path=cast["chosen"])

    board = attempt("board", _board, progress=0.45)
    if not any(item.get("chosen") for item in board.get("items") or []):
        raise RuntimeError("分镜板一张都没生成")
    mark("board", "done")

    audio_mode = "native"
    oneshot_done = False
    if native and fidelity != "structure" and (product.get("cast") or {}).get("chosen"):
        # Preferred path: one clip with the whole dialogue (no TTS, no lip-sync pass).
        try:
            jobs.update(job, progress=0.65)
            from adplus.recreate import asr as asr_mod
            from adplus.recreate import render_oneshot

            film = render_oneshot.render_oneshot(
                skeleton, script, product, root / "p3",
                cast=product["cast"]["chosen"], resolution=resolution,
                product_image=product.get("image") or None,
                seconds_override=int(seconds_override) if seconds_override else None,
            )
            transcript = asr_mod.transcribe(film["clip"])
            segments = transcript.get("segments") or []
            plan = assemble_mod.assemble_oneshot(film["clip"], segments, root / "p3", script=script)
            plan["dialogue_chars"] = sum(len(str(seg.get("text") or "")) for seg in segments)
            (root / "p3" / "timeline.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            shots = {"version": 1, "provider": "oneshot", "shots": {"oneshot": {"mode": "native", "clip": film["clip"], "status": "ok"}}}
            oneshot_done = True
        except Exception:  # noqa: BLE001 - fall through to per-beat native
            oneshot_done = False

    if not oneshot_done:
        try:
            shots = render_native.render_native(
                skeleton, script, board, root / "p3", resolution=resolution,
            )
            ok = [row for row in shots["shots"].values() if row.get("status") == "ok"]
            if not ok:
                raise RuntimeError("native 一条都没生成")
        except Exception:
            from adplus.recreate import render_cli, render_seedance

            try:
                shots = render_seedance.render_seedance(skeleton, script, root / "p3")
                ok = [row for row in shots["shots"].values() if row.get("status") == "ok"]
                if not ok:
                    raise RuntimeError("seedance 也没生成")
                audio_mode = "tts"
            except Exception:
                shots = render_cli.render(skeleton, board, script, root / "p3", mode="still")
                audio_mode = "tts"
    mark("shots", "done")

    jobs.update(job, progress=0.85)
    if oneshot_done:
        report = qa_mod.check(plan["output"], skeleton, script, timeline=plan)
        _write(root / "p3" / "qa.json", report)
    else:
        plan = assemble_mod.assemble(skeleton, script, shots.get("shots") or {}, root / "p3", audio_mode=audio_mode)
        report = qa_mod.check(plan["output"], skeleton, script, timeline=plan)
        _write(root / "p3" / "qa.json", report)
    mark("finish", "done")
    jobs.update(job, progress=1.0)
