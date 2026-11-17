"""Deterministic compose for routes whose shots already have bound media.

This is not a video generator: it concatenates user-approved/bound shot media
into one reviewable file.  Generation stays with the provider/tool layer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from adplus import jobs as job_store
from adplus import product_composite, products, project_store

FPS = 30


def _resolve(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = project_store.PROJECTS.parent / path
    return path.resolve() if path.is_file() else None


def _shot_source(shot: dict[str, Any]) -> Path | None:
    refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    for value in (
        refs.get("source_video"),
        refs.get("video_path"),
        refs.get("source_path"),
        shot.get("preview"),
    ):
        path = _resolve(str(value) if value else None)
        if path is not None:
            return path
    return None


def start(project_id: str) -> dict[str, Any]:
    project = project_store.load_project(project_id)
    version = project_store.ensure_version(project_id)
    if project is None or version is None:
        raise FileNotFoundError(project_id)
    shots = version.get("shots") or []
    if not shots:
        raise ValueError("还没有分镜")
    sources = [_shot_source(shot) for shot in shots]
    missing = [index + 1 for index, source in enumerate(sources) if source is None]
    if missing:
        raise ValueError(f"还有 {len(missing)} 个镜头没有绑定素材：{missing}")
    output = project_store.PROJECTS / project_id / "renders" / f"{project_id}-avatar-{int(time.time())}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    job = job_store.start(
        "avatar_compose", project_id,
        frames_total=max(1, round(float(version.get("duration_s") or project.get("duration_s") or 15) * FPS)),
    )
    threading.Thread(target=_run, args=(project_id, job, [path for path in sources if path], output), daemon=True).start()
    return {"job_id": job["id"], "project_id": project_id, "output": str(output)}


def _run(project_id: str, job: dict[str, Any], sources: list[Path], output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    temp_root = Path(tempfile.mkdtemp(prefix="adplus-asset-compose-"))
    try:
        parts: list[Path] = []
        for index, source in enumerate(sources):
            if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                part = temp_root / f"part_{index}.mp4"
                subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(source), "-t", "2.5",
                     "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                     "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(part)],
                    check=True, capture_output=True, timeout=120,
                )
                parts.append(part)
            else:
                parts.append(source)
            job_store.update(job, progress=0.15 + 0.55 * (index + 1) / len(sources))
        concat = temp_root / "concat.txt"
        concat.write_text("\n".join(f"file '{path.as_posix()}'" for path in parts), encoding="utf-8")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
             "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(output)],
            check=True, capture_output=True, timeout=600,
        )
        project = project_store.load_project(project_id) or {}
        product_id = project.get("product_id")
        plate_result = None
        label_result = None
        if product_id:
            product = products.load_product(str(product_id))
            hero = (product or {}).get("hero_path")
            if product and hero:
                hero_path = Path(hero) if Path(hero).is_absolute() else project_store.PROJECTS.parent / hero
                plate_output = output.with_name(f"{output.stem}_plate{output.suffix}")
                plate_result = product_composite.composite_files(
                    output, hero_path, plate_output, start_s=1.0, end_s=5.0,
                )
                if plate_result.get("success"):
                    plate_output.replace(output)
                label_result = product_composite.label_qa_for(product, hero_path)
        rel = str(output.resolve().relative_to(project_store.PROJECTS.parent.resolve()))
        version = project_store.ensure_version(project_id)
        if version is not None:
            project = project_store.load_project(project_id) or {}
            settings = project.get("production_settings") or {}
            version["render"] = {
                "path": rel, "width": 1080, "height": 1920, "duration_s": None, "fps": FPS,
                "settings_revision": int(settings.get("revision") or 1),
            }
            version["status"] = "review"
            project_store.save_version(version)
        project_store.update_project(project_id, {"status": "review"})
        review_path = project_store.PROJECTS / project_id / "artifacts" / "final_review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_status = "pass" if (label_result is None or label_result.get("verdict") == "pass") else "revise"
        review_path.write_text(json.dumps({
            "status": review_status,
            "checks": {
                "technical_probe": {"verdict": "pass", "detail": "bound shot media concatenated"},
                "label_qa": label_result or {"verdict": "not_applicable"},
            },
            "issues_found": [] if review_status == "pass" else [str((label_result or {}).get("detail") or "label QA failed")],
            "metadata": {"product_plate": plate_result, "label_qa": label_result},
            "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        job_store.finish(job, "done", output=rel)
    except Exception as exc:
        job_store.finish(job, "failed", error=str(exc)[:1000])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
