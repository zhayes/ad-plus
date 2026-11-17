"""Media primitives for the recreate pipeline.

Deliberately dependency-light: ffmpeg/ffprobe for decode, numpy for audio.
faster-whisper is only imported by :mod:`adplus.recreate.asr`, never here, so
the rest of the pipeline runs on a machine without the speech model.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

FFMPEG = os.environ.get("ADPLUS_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("ADPLUS_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(args: list[str], *, timeout: int = 120, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=not binary,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def probe(path: str | Path) -> dict[str, Any]:
    """Return the facts every later stage depends on, normalised."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    proc = _run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout=60)
    if proc.returncode != 0:
        raise ValueError(f"ffprobe failed: {proc.stderr[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError("no video stream")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0.0)
    if height > width * 1.15:
        aspect = "9:16"
    elif width > height * 1.15:
        aspect = "16:9"
    else:
        aspect = "1:1"
    return {
        "path": str(path),
        "duration_s": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")), 3),
        "aspect": aspect,
        "video_codec": video.get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
        "has_audio": audio is not None,
        "size_bytes": int((data.get("format") or {}).get("size") or path.stat().st_size),
    }


def _fraction(value: Any) -> float:
    try:
        num, den = str(value or "0/1").split("/", 1)
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def audio_f32(path: str | Path, sample_rate: int = 16000) -> np.ndarray:
    """Decode mono float32 PCM through ffmpeg.

    Reading a pipe instead of calling ``faster_whisper.decode_audio`` keeps the
    pipeline independent of PyAV's changing API (the installed ``av`` renamed
    ``metadata_errors``, which broke the vendor transcriber tool).
    """
    proc = _run(
        [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        timeout=300,
        binary=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"audio decode failed: {proc.stderr[:300]!r}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def detect_cuts(path: str | Path, duration: float, threshold: float = 0.18) -> list[float]:
    """Scene-change timestamps, merged and clamped away from the edges."""
    proc = _run(
        [FFMPEG, "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        timeout=300,
    )
    import re

    times = sorted({round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", proc.stderr or "")})
    merged: list[float] = []
    for t in times:
        if 0.2 < t < duration - 0.2 and (not merged or t - merged[-1] >= 0.35):
            merged.append(t)
    return merged


def extract_frame(path: str | Path, at: float, out: str | Path, width: int = 640) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", f"scale={max(80, width)}:-2", "-q:v", "3", str(out)],
        timeout=60,
    )
    if proc.returncode != 0 or not out.is_file():
        raise ValueError(f"frame extraction failed at {at:.2f}s: {proc.stderr[:200]}")
    return out


def shot_ranges(cuts: list[float], duration: float, min_len: float = 0.35) -> list[tuple[float, float]]:
    points = [0.0]
    for t in cuts:
        if t - points[-1] >= min_len:
            points.append(round(t, 3))
    if duration - points[-1] > 0.05:
        points.append(round(duration, 3))
    return list(zip(points[:-1], points[1:]))


def sample_times(shots: list[tuple[float, float]], max_frames: int = 8) -> list[tuple[float, int]]:
    """Pick one representative frame per shot, capped at ``max_frames``.

    Long shots get their sample placed 40% in, which avoids transition frames
    and usually lands on the performance rather than the entrance.
    """
    picked: list[tuple[float, int]] = []
    for index, (start, end) in enumerate(shots):
        picked.append((round(start + (end - start) * 0.4, 3), index))
    if len(picked) <= max_frames:
        return picked
    # Keep the first, the last, and an even spread in between.
    step = (len(picked) - 1) / (max_frames - 1)
    keep = {round(i * step) for i in range(max_frames)}
    return [item for i, item in enumerate(picked) if i in keep]
