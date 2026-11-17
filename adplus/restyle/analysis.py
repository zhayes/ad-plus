"""Video analysis for Restyle: probe, cuts, keyframes, captions, groups.

The analysis is deliberately local and deterministic.  It produces the
read-only blueprint the UI shows as the "read card"; it does not spend money
and does not call a model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from adplus import project_store
from adplus.restyle import plans
from adplus.paths import PROJECTS

FFMPEG = os.environ.get("ADPLUS_FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("ADPLUS_FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
TESSERACT = os.environ.get("ADPLUS_TESSERACT") or shutil.which("tesseract")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECTS.parent.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _fraction(value: Any) -> float:
    try:
        num, den = str(value or "0/1").split("/", 1)
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise ValueError(f"ffprobe failed: {proc.stderr[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError("video stream not found")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    if height > width * 1.15:
        aspect = "9:16"
    elif width > height * 1.15:
        aspect = "16:9"
    else:
        aspect = "1:1"
    return {
        "duration_s": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")) or 30.0, 3),
        "aspect": aspect,
        "has_audio": bool(audio),
        "audio_codec": (audio or {}).get("codec_name"),
        "video_codec": video.get("codec_name"),
        "size_bytes": int((data.get("format") or {}).get("size") or path.stat().st_size),
    }


def detect_cuts(path: str | Path, duration: float, threshold: float = 0.18) -> list[float]:
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path), "-vf",
         f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=180, creationflags=_NO_WINDOW,
    )
    cuts = [round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", proc.stderr or "")]
    cuts = sorted({c for c in cuts if 0.2 < c < duration - 0.2})
    merged: list[float] = []
    for cut in cuts:
        if not merged or cut - merged[-1] >= 0.35:
            merged.append(cut)
    if len(merged) < 1:
        step = 2.5
        merged = [round(i * step, 3) for i in range(1, int(duration // step) + 1)]
    points = [0.0] + merged + [round(duration, 3)]
    # guard against tiny shots
    shots: list[float] = [0.0]
    for point in points[1:]:
        if point - shots[-1] >= 0.35:
            shots.append(point)
    if shots[-1] < duration:
        shots.append(round(duration, 3))
    return shots


def extract_frame(path: str | Path, t: float, out: Path, width: int = 360) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={max(80, width)}:-1", "-q:v", "3", str(out)],
        capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0 or not out.is_file():
        raise ValueError(f"keyframe extraction failed at {t:.2f}s: {proc.stderr[:200]}")
    return out


def _caption_crop(frame_path: Path) -> tuple[Any, tuple[int, int, int, int]]:
    from PIL import Image, ImageFilter
    import numpy as np

    image = Image.open(frame_path).convert("RGB")
    width, height = image.size
    top = int(height * 0.72)
    crop = image.crop((0, top, width, height))
    arr = np.asarray(crop).astype(np.int16)
    red, green, blue = arr[..., 0], arr[..., 1], arr[..., 2]
    mask = (red > 140) & (green > 120) & (blue < 125) & (red - blue > 55) & (green - blue > 35)
    if int(mask.sum()) < 60:
        return image, (0, 0, 0, 0)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    x0, x1 = int(cols.min()), int(cols.max())
    y0, y1 = int(rows.min()), int(rows.max())
    box = (x0, y0 + top, x1 - x0, y1 - y0)
    pad = 6
    xa, ya = max(0, x0 - pad), max(0, y0 - pad)
    xb, yb = min(mask.shape[1], x1 + pad), min(mask.shape[0], y1 + pad)
    binary = np.where(mask[ya:yb, xa:xb], 0, 255).astype(np.uint8)
    prepared = Image.fromarray(binary)
    prepared = prepared.resize((prepared.width * 4, prepared.height * 4), Image.LANCZOS)
    return prepared, box


def read_caption(frame_path: Path) -> dict[str, Any]:
    if not TESSERACT:
        return {"text": "", "bbox": None, "status": "unavailable"}
    try:
        prepared, box = _caption_crop(frame_path)
        if box[2] <= 0 or box[3] <= 0:
            return {"text": "", "bbox": None, "status": "empty"}
        tmp = frame_path.with_name(frame_path.stem + "_caption.png")
        prepared.save(tmp)
        proc = subprocess.run(
            [TESSERACT, str(tmp), "stdout", "-l", "chi_sim", "--psm", "7"],
            capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
        )
        text = re.sub(r"\s+", "", proc.stdout or "")
        if len(text) < 2:
            proc = subprocess.run(
                [TESSERACT, str(tmp), "stdout", "-l", "chi_sim", "--psm", "11"],
                capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
            )
            text = re.sub(r"\s+", "", proc.stdout or "")
        tmp.unlink(missing_ok=True)
        if len(text) > 40:  # likely a mask/OCR collision, not a caption
            text = ""
        return {
            "text": text[:40],
            "bbox": list(box),
            "status": "review" if len(text) >= 2 else "empty",
        }
    except Exception as exc:  # OCR failure must not fail analysis
        return {"text": "", "bbox": None, "status": f"error:{str(exc)[:80]}"}


def _histogram(frame_path: Path, box: tuple[float, float, float, float], bins: int = 6) -> list[float]:
    from PIL import Image
    import numpy as np

    image = Image.open(frame_path).convert("RGB")
    width, height = image.size
    left, top, right, bottom = box
    crop = image.crop((int(width * left), int(height * top), int(width * right), int(height * bottom)))
    crop = crop.resize((48, 48), Image.BILINEAR)
    arr = np.asarray(crop).astype(np.float32) / 255.0
    hist, _ = np.histogramdd(
        arr.reshape(-1, 3), bins=(bins, bins, bins), range=((0, 1), (0, 1), (0, 1))
    )
    hist = hist.reshape(-1)
    total = float(hist.sum()) or 1.0
    return (hist / total).tolist()


def _distance(a: list[float], b: list[float]) -> float:
    return float(sum((x - y) ** 2 for x, y in zip(a, b)))


def _kmeans(vectors: list[list[float]], k: int, iterations: int = 20) -> list[int]:
    n = len(vectors)
    if n == 0:
        return []
    k = max(1, min(k, n))
    if k == 1:
        return [0] * n
    indices = [round(i * (n - 1) / max(1, k - 1)) for i in range(k)]
    centers = [vectors[i][:] for i in indices]
    labels = [0] * n
    for _ in range(iterations):
        changed = False
        for i, vector in enumerate(vectors):
            best = min(range(k), key=lambda c: _distance(vector, centers[c]))
            if labels[i] != best:
                labels[i] = best
                changed = True
        for c in range(k):
            members = [vectors[i] for i in range(n) if labels[i] == c]
            if members:
                centers[c] = [sum(col) / len(members) for col in zip(*members)]
        if not changed:
            break
    return labels


def _group(shots: list[dict[str, Any]], hists: list[list[float]], key: str, k: int, label: str) -> list[dict[str, Any]]:
    labels = _kmeans(hists, k)
    buckets: dict[int, list[str]] = {}
    for shot, label_index in zip(shots, labels):
        buckets.setdefault(label_index, []).append(str(shot["id"]))
    ordered = sorted(buckets.items(), key=lambda item: min(int(s["index"]) for s in shots if str(s["id"]) in item[1]))
    groups = []
    for index, (_, shot_ids) in enumerate(ordered, 1):
        first = next(s for s in shots if str(s["id"]) == shot_ids[0])
        groups.append({
            "id": f"{key}{index:02d}",
            "label": f"{label} {index}",
            "shot_ids": shot_ids,
            "thumb": first.get("keyframe"),
        })
    for shot, label_index in zip(shots, labels):
        group_id = next(
            g["id"] for g in groups if str(shot["id"]) in g["shot_ids"]
        )
        shot.setdefault("groups", {})[key] = group_id
    return groups


def analyze_project(project_id: str, progress: Callable[[float], None] | None = None) -> dict[str, Any]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    root = PROJECTS / project_id / "restyle"
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    source_path = PROJECTS.parent / str(source["path"]) if not Path(source["path"]).is_absolute() else Path(source["path"])
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    meta = source.get("probe") or probe(source_path)
    duration = float(meta.get("duration_s") or 0)
    points = detect_cuts(source_path, duration)
    shots: list[dict[str, Any]] = []
    thumbs = root / "thumbs"
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        shot_id = f"s{index + 1:02d}"
        midpoint = (start + end) / 2
        frame = thumbs / f"{shot_id}.jpg"
        extract_frame(source_path, midpoint, frame, width=720)
        caption = read_caption(frame)
        shots.append({
            "id": shot_id,
            "index": index + 1,
            "start_s": round(start, 3),
            "end_s": round(end, 3),
            "duration_s": round(end - start, 3),
            "keyframe": _rel(frame),
            "caption": caption,
            "groups": {},
            "risk": {"score": 0.2, "reasons": []},
            "suggested": "change",
        })
        if progress:
            progress(min(1.0, (index + 1) / max(1, len(points) - 1) * 0.8))

    background_hists = [_histogram(PROJECTS.parent / s["keyframe"], (0.05, 0.05, 0.95, 0.65)) for s in shots]
    outfit_hists = [_histogram(PROJECTS.parent / s["keyframe"], (0.25, 0.15, 0.75, 0.65)) for s in shots]
    scene_k = min(6, max(1, round(len(shots) / 5))) if len(shots) else 1
    outfit_k = min(4, max(1, round(len(shots) / 8))) if len(shots) else 1
    scenes = _group(shots, background_hists, "sc", scene_k, "场景")
    outfits = _group(shots, outfit_hists, "of", outfit_k, "造型")

    captions = [s for s in shots if (s.get("caption") or {}).get("text")]
    video_type = "product_demo" if len(shots) >= 10 and duration / max(1, len(shots)) < 2.0 else "talking_head"
    blueprint = {
        "version": 1,
        "video_type": video_type,
        "source": source,
        "shots": shots,
        "groups": {
            "scenes": scenes,
            "outfits": outfits,
            "products": [],
            "objects": [],
        },
        "audio": {"mode": "keep", "has_speech": None, "transcript": None},
        "suggestions": {
            "change_shot_ids": [s["id"] for s in shots],
            "keep_shot_ids": [],
            "reason": "P1 骨架：全部镜头先标记为可改，风险与保留建议在 P2 细化",
        },
        "caption_count": len(captions),
        "analyzed_at": _now(),
    }
    (root / "blueprint.json").write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_path = root / "plan.json"
    if plan_path.is_file():
        try:
            current_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            synced, changed = plans.sync_groups(current_plan, blueprint)
            if changed:
                plan_path.write_text(json.dumps(synced, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    if progress:
        progress(0.95)
    project_store.update_project(project_id, {
        "duration_s": duration,
        "aspect": meta.get("aspect") or project.get("aspect") or "9:16",
        "cover": shots[0]["keyframe"] if shots else None,
    })
    if progress:
        progress(1.0)
    return blueprint
