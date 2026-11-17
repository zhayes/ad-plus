"""Audio-only generation for the OpenMontage ``assets`` stage.

Audio is generated before visuals.  Voice changes only invalidate audio; a
visual job never calls TTS.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from adplus import canonical_artifacts, jobs as job_store, personas, project_store, tts


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_store.PROJECTS.parent.resolve()))
    except (ValueError, OSError):
        return str(path)


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return round(float(json.loads(result.stdout)["format"]["duration"]), 3)
    except Exception:
        return 0.0


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fit_audio(path: Path, duration: float, shot_duration: float, mode: str) -> Path:
    if duration <= shot_duration + 0.05 or mode == "pad":
        return path
    target = path.with_name(f"{path.stem}_fit{path.suffix}")
    if mode == "stretch":
        tempo = max(0.5, min(2.0, duration / max(0.2, shot_duration)))
        filter_arg = f"atempo={tempo:.4f}"
    else:
        filter_arg = "anull"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-t", f"{shot_duration:.3f}",
             "-af", filter_arg, "-ar", "16000", "-ac", "1", str(target)],
            check=True, capture_output=True, timeout=60,
        )
        target.replace(path)
    except Exception:
        target.unlink(missing_ok=True)
    return path


def _script_narration(project_id: str, shot: dict[str, Any]) -> str:
    """Use the quoted spoken line from script.json for this shot."""
    path = project_store.PROJECTS / project_id / "artifacts" / "script.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    lines = payload.get("lines") if isinstance(payload, dict) else []
    if not isinstance(lines, list) or not lines:
        return ""
    version = project_store.ensure_version(project_id) or {}
    content_shots = [
        item for item in version.get("shots") or []
        if str(item.get("description") or item.get("on_screen_text") or item.get("narration") or "").strip()
    ]
    ids = [str(item.get("id")) for item in content_shots]
    try:
        index = ids.index(str(shot.get("id")))
    except ValueError:
        try:
            index = max(0, int(shot.get("index") or 1) - 1)
        except (TypeError, ValueError):
            index = 0
    if index >= len(lines):
        return ""
    line = lines[index]
    text = str(line.get("text") or "").strip()
    quoted = re.findall(r"「([^」]+)」", text)
    if quoted:
        return "".join(quoted).strip()
    return re.sub(r"^\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?s\s*[：:]\s*", "", text).strip()


def _narration_for(project_id: str, shot: dict[str, Any]) -> str:
    explicit = str(shot.get("narration") or "").strip()
    if explicit:
        return explicit
    if not str(shot.get("description") or shot.get("on_screen_text") or "").strip():
        return ""
    return _script_narration(project_id, shot) or str(shot.get("on_screen_text") or "").strip()


def _mode_for(shot: dict[str, Any], settings: dict[str, Any]) -> str:
    audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    mode = str(audio.get("mode") or (settings.get("audio") or {}).get("mode") or "silent")
    method = str(shot.get("production_method") or "")
    kind = str(shot.get("kind") or "")
    if method in {"avatar", "lip_sync"} or kind == "talking_head":
        return "external_tts"
    return mode


def _voice_for(shot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    project_audio = settings.get("audio") if isinstance(settings.get("audio"), dict) else {}
    shot_audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    persona = personas.load_persona(str(shot["persona_id"])) if shot.get("persona_id") else None
    persona_voice = (persona or {}).get("voice") if isinstance((persona or {}).get("voice"), dict) else {}
    # shot override > project > persona > local default
    provider = shot_audio.get("provider") or project_audio.get("provider") or persona_voice.get("provider") or "local"
    voice_id = shot_audio.get("voice_id") or project_audio.get("voice_id") or persona_voice.get("voice_id") or "Tingting"
    language = shot_audio.get("language") or project_audio.get("language") or persona_voice.get("language") or "zh-CN"
    speed = shot_audio.get("speed") or project_audio.get("speed") or persona_voice.get("speed") or 1.0
    return {"provider": provider, "voice_id": voice_id, "language": language, "speed": float(speed)}


def synthesize_shot(project_id: str, shot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    mode = _mode_for(shot, settings)
    if mode in {"silent", "model_native"}:
        return {"status": "not_required", "mode": mode, "path": None}
    if mode != "external_tts":
        raise ValueError(f"unsupported audio mode: {mode}")
    text = _narration_for(project_id, shot)
    if not text:
        raise ValueError("镜头没有台词，无法生成配音")
    voice = _voice_for(shot, settings)
    if voice["provider"] != "local":
        raise ValueError(f"{voice['provider']} TTS 未配置；先使用本地声音")
    out_dir = project_store.PROJECTS / project_id / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{shot['id']}_{int(time.time())}.wav"
    generated = tts.synthesize(
        text, output, voice=str(voice["voice_id"]), language=str(voice["language"]), speed=float(voice["speed"]),
    )
    duration = _probe_duration(output)
    fit = str((settings.get("audio") or {}).get("fit") or "trim")
    _fit_audio(output, duration, float(shot.get("duration_s") or 2.5), fit)
    duration = _probe_duration(output)
    return {
        "status": "ready",
        "mode": mode,
        "path": _rel(output),
        "duration_s": duration,
        "provider": voice["provider"],
        "voice_id": voice["voice_id"],
        "language": voice["language"],
        "speed": voice["speed"],
        "fit": fit,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "audio_hash": _sha(output),
        "audio_revision": int((settings.get("revisions") or {}).get("audio") or 1),
        "generated_at": _now(),
    }


def backfill_narration(project_id: str) -> dict[str, Any]:
    version = project_store.ensure_version(project_id)
    if version is None:
        raise ValueError("还没有分镜")
    updated = 0
    for shot in version.get("shots") or []:
        if str(shot.get("narration") or "").strip():
            continue
        text = _narration_for(project_id, shot)
        if text:
            project_store.update_shot(project_id, version["id"], str(shot.get("id")), {"narration": text})
            updated += 1
    return {"project_id": project_id, "updated": updated}


def audio_manifest(project_id: str, version: dict[str, Any]) -> dict[str, Any]:
    tracks = []
    for shot in version.get("shots") or []:
        audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
        if audio.get("status") == "ready" and audio.get("path"):
            tracks.append({
                "id": f"audio_{shot.get('id')}",
                "shot_id": str(shot.get("id")),
                "path": str(audio["path"]),
                "duration_s": float(audio.get("duration_s") or 0),
                "provider": audio.get("provider"),
                "voice_id": audio.get("voice_id"),
                "mode": audio.get("mode"),
                "audio_revision": audio.get("audio_revision"),
            })
    return {"version": "1.0", "tracks": tracks, "metadata": {"adplus_project_id": project_id, "settings_revision": (project_store.load_project(project_id) or {}).get("production_settings", {}).get("revision")}}


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
        current = next((item for item in (project_store.load_version(project_id, version["id"]) or {}).get("shots") or [] if str(item.get("id")) == str(shot.get("id"))), shot)
        if not force and (current.get("audio") or {}).get("status") == "ready":
            job_store.update(job, progress=(index + 1) / max(1, len(shots)))
            continue
        try:
            derived = _narration_for(project_id, current)
            if derived and not str(current.get("narration") or "").strip():
                project_store.update_shot(project_id, version["id"], str(shot.get("id")), {"narration": derived})
                current["narration"] = derived
            audio = synthesize_shot(project_id, current, settings)
            project_store.update_shot(project_id, version["id"], str(shot.get("id")), {
                "audio": {**(current.get("audio") or {}), **audio},
                "status": "ready" if audio.get("status") == "ready" else current.get("status", "planned"),
            })
        except Exception as exc:
            failed.append(f"{shot.get('id')}: {exc}")
            project_store.update_shot(project_id, version["id"], str(shot.get("id")), {
                "audio": {**(current.get("audio") or {}), "status": "failed", "error": str(exc)},
            })
        job_store.update(job, progress=(index + 1) / max(1, len(shots)))
    version = project_store.load_version(project_id, version["id"])
    if version:
        manifest = audio_manifest(project_id, version)
        canonical_artifacts.write(project_id, "audio_manifest", manifest, validate=False)
    if failed:
        job_store.finish(job, "failed", error="; ".join(failed)[:2000])
    else:
        job_store.finish(job, "done", output=f"{len(shots)} audio tracks")


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
        raise ValueError("没有可配音的镜头")
    job = job_store.start("audio_generation", project_id, log_tail=[], shots_total=len(shots))
    threading.Thread(target=_run, args=(project_id, job, shots, force), daemon=True).start()
    return {"job_id": job["id"], "project_id": project_id, "shots": len(shots)}
