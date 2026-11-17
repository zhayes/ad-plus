"""Batch generation for the OpenMontage ``assets`` stage.

The runner is deliberately stage-scoped: it iterates storyboard shots, resolves
the selected model/voice policy, calls the registered tool, and writes the
canonical asset manifest.  It is not a second pipeline.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any

from adplus import canonical_artifacts, capabilities, digital_human, jobs as job_store, pipeline_adapter, pipeline_runner, product_composite, products, project_store


def _shot_kind(shot: dict[str, Any]) -> str:
    explicit = str(shot.get("kind") or "")
    if explicit in {"talking_head", "broll", "product", "still", "local_motion"}:
        return explicit
    method = str(shot.get("production_method") or "")
    if method in {"avatar", "lip_sync"}:
        return "talking_head"
    if method == "product_composite":
        return "product"
    return "broll"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_store.PROJECTS.parent.resolve()))
    except (ValueError, OSError):
        return str(path)


def _audio_path(shot: dict[str, Any]) -> str | None:
    refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    spec = shot.get("generation_spec") if isinstance(shot.get("generation_spec"), dict) else {}
    audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    return str(audio.get("path") or spec.get("audio_path") or refs.get("audio") or "") or None


def _generate_talking_head(project_id: str, shot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    generation = settings.get("visual") or settings.get("generation") or {}
    profile_id = str(generation.get("talking_head_profile") or "")
    if not profile_id:
        raise ValueError("没有配置口播模型")
    audio = _audio_path(shot)
    if not audio:
        raise ValueError("口播镜头缺少音频；请先在配音步骤生成")
    take = digital_human.plan(
        project_id,
        shot_id=str(shot["id"]),
        profile_id=profile_id,
        persona_id=shot.get("persona_id"),
        product_id=shot.get("product_id"),
        audio_path=audio,
        prompt=str(shot.get("narration") or shot.get("description") or ""),
    )
    if take.get("status") != "ready":
        raise ValueError("; ".join(take.get("blockers") or ["口播预检未通过"]))
    result = digital_human.execute(take)
    if not result.get("result", {}).get("success"):
        raise ValueError(str(result.get("result", {}).get("error") or "口播生成失败"))
    audio_hash = ""
    try:
        audio_file = Path(audio) if Path(audio).is_absolute() else project_store.PROJECTS.parent / audio
        digest = hashlib.sha256()
        with audio_file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        audio_hash = digest.hexdigest()
    except OSError:
        pass
    return {
        "path": result["output_path"],
        "cost_usd": float(result.get("result", {}).get("cost_usd") or 0),
        "profile": profile_id,
        "audio": audio,
        "audio_hash": audio_hash,
    }


def _generate_broll(project_id: str, shot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    generation = settings.get("visual") or settings.get("generation") or {}
    audio_cfg = settings.get("audio") or {}
    output = settings.get("output") or {}
    profile_id = str(generation.get("broll_profile") or "")
    if not profile_id:
        raise ValueError("没有配置 B-roll 模型")
    from tools.tool_registry import registry

    registry.discover()
    profile = capabilities.get_profile(profile_id) or {}
    tool_name = str(profile.get("tool") or "")
    if profile_id.startswith("seedance"):
        tool = registry.get(tool_name)
        if tool is None:
            raise ValueError(f"OpenMontage tool not registered: {tool_name}")
        out = project_store.PROJECTS / project_id / "renders" / f"broll_{shot['id']}_{int(time.time())}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        duration = max(4, min(15, int(round(float(shot.get("duration_s") or 4)))))
        result = tool.execute({
            "task_action": "generate",
            "operation": "text_to_video",
            "model_variant": "2.5" if profile_id == "seedance-2.5" else "standard",
            "prompt": str(shot.get("description") or shot.get("narration") or "advertisement b-roll"),
            "duration": duration,
            "resolution": str(output.get("resolution") or "480p"),
            "aspect_ratio": str(output.get("aspect") or "9:16"),
            "generate_audio": str(audio_cfg.get("mode") or generation.get("audio_mode") or "") == "model_native",
            "output_path": str(out),
        })
        if not getattr(result, "success", False):
            raise ValueError(str(getattr(result, "error", "B-roll 生成失败")))
        return {
            "path": _rel(Path(str(result.data.get("output") or out))),
            "cost_usd": float(getattr(result, "cost_usd", 0) or 0),
            "profile": profile_id,
        }
    raise ValueError(f"{profile_id} 还没有批量 B-roll adapter")


def generate_shot(project_id: str, shot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    kind = _shot_kind(shot)
    if kind == "local_motion":
        raise ValueError("local_motion 镜头由本地合成器生成，不需要外部素材")
    if kind == "talking_head":
        return _generate_talking_head(project_id, shot, settings)
    result = _generate_broll(project_id, shot, settings)
    if kind == "product" and shot.get("product_id"):
        product = products.load_product(str(shot["product_id"]))
        hero = (product or {}).get("hero_path")
        if product and hero and product.get("locked"):
            base = project_store.PROJECTS.parent / result["path"] if not Path(result["path"]).is_absolute() else Path(result["path"])
            plate = base.with_name(f"{base.stem}_plate.mp4")
            try:
                overlaid = product_composite.composite_files(
                    base, project_store.PROJECTS.parent / hero if not Path(hero).is_absolute() else hero,
                    plate, start_s=0, end_s=max(0.8, float(shot.get("duration_s") or 2.5)),
                )
                if overlaid.get("success"):
                    result["path"] = _rel(plate)
                    result["product_plate"] = True
            except Exception:
                pass
    return result


def _run(project_id: str, job: dict[str, Any], shots: list[dict[str, Any]], force: bool) -> None:
    project = project_store.load_project(project_id) or {}
    settings = project.get("production_settings") or {}
    version = project_store.ensure_version(project_id)
    if version is None:
        job_store.finish(job, "failed", error="没有分镜版本")
        return
    failed: list[str] = []
    for index, shot in enumerate(shots):
        if job_store.cancel_requested(project_id, job["id"]):
            job_store.finish(job, "cancelled", error="用户取消")
            return
        shot_id = str(shot.get("id"))
        if not force and shot.get("preview"):
            job_store.update(job, progress=(index + 1) / max(1, len(shots)), log_tail=job.get("log_tail", [])[-20:] + [f"skip {shot_id}: existing"])
            continue
        try:
            result = generate_shot(project_id, shot, settings)
            project_store.update_shot(
                project_id, version["id"], shot_id,
                {
                    "preview": result["path"],
                    "asset_refs": {**(shot.get("asset_refs") or {}), "source_video": result["path"]},
                    "generation_spec": {
                        **(shot.get("generation_spec") or {}),
                        "profile_id": result["profile"],
                        **({"audio_path": result["audio"], "audio_hash": result.get("audio_hash")} if result.get("audio") else {}),
                    },
                    "status": "ready",
                    "cost_usd": result["cost_usd"],
                },
            )
        except Exception as exc:
            failed.append(f"{shot_id}: {exc}")
            project_store.update_shot(project_id, version["id"], shot_id, {"status": "needs_rework"})
        job_store.update(
            job,
            progress=(index + 1) / max(1, len(shots)),
            log_tail=(job.get("log_tail") or [])[-20:] + [f"{shot_id}: {'failed' if failed and failed[-1].startswith(shot_id) else 'done'}"],
        )
    version = project_store.load_version(project_id, version["id"])
    all_ready = bool(version and all(shot.get("preview") for shot in version.get("shots") or []))
    if version:
        version["settings_revision"] = int(settings.get("revision") or 1)
        version = project_store.save_version(version)
    if all_ready and version:
        manifest = canonical_artifacts.asset_manifest_from_version(project, version)
        canonical_artifacts.write(project_id, "asset_manifest", manifest)
        route_id = str((project.get("route") or {}).get("id") or "avatar_spokesperson") if isinstance(project.get("route"), dict) else "avatar_spokesperson"
        pipeline = pipeline_adapter.pipeline_for_route(route_id)
        pipeline_runner.sync_and_bootstrap(project_id, version.get("id"), approve=True, pipeline=pipeline)
        artifacts = {"asset_manifest": manifest}
        audio_manifest = canonical_artifacts.read(project_id, "audio_manifest")
        if audio_manifest:
            artifacts["audio_manifest"] = audio_manifest
        pipeline_runner.write_stage(
            project_id, "assets", artifacts,
            approved=True, pipeline=pipeline,
        )
    if failed:
        job_store.finish(job, "failed", error="; ".join(failed)[:2000])
    else:
        job_store.finish(job, "done", output=f"{len(shots)} shots")


def start(project_id: str, *, force: bool = False, shot_ids: list[str] | None = None) -> dict[str, Any]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    version = project_store.ensure_version(project_id)
    if version is None:
        raise ValueError("还没有分镜")
    shots = list(version.get("shots") or [])
    if shot_ids:
        wanted = set(shot_ids)
        shots = [shot for shot in shots if str(shot.get("id")) in wanted]
    if not shots:
        raise ValueError("没有可生成的镜头")
    job = job_store.start("asset_generation", project_id, log_tail=[], shots_total=len(shots))
    threading.Thread(target=_run, args=(project_id, job, shots, force), daemon=True).start()
    return {"job_id": job["id"], "project_id": project_id, "shots": len(shots)}
