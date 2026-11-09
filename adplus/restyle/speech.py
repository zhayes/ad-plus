"""Per-shot speech / lip-sync mode detection.

Why this exists: a rewritten ad may have on-camera speech, background
voice-over, or no speech at all.  Running lip-sync on every shot wastes money
and produces fake mouths on B-roll.  This module classifies each shot:

    on_camera | voiceover | no_speech | unknown

Signals:
  * audio activity (FFmpeg PCM RMS, no cloud/ASR required)
  * face presence (MediaPipe FaceDetector task)
  * mouth openness (MediaPipe FaceLandmarker on the face crop)
  * correlation between mouth motion and audio energy

It is deliberately local and deterministic.  ASR/transcript can refine the
result later, but is not required for the mode decision.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = Path(os.environ.get("ADPLUS_FACE_MODEL_DIR") or ROOT / "assets" / "models")
FACE_MODEL = MODEL_DIR / "blaze_face_short_range.tflite"
LANDMARK_MODEL = MODEL_DIR / "face_landmarker.task"
FFMPEG = os.environ.get("ADPLUS_FFMPEG") or "ffmpeg"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# MediaPipe FaceMesh mouth points: upper lip 13, lower lip 14.


def _ffmpeg_pcm(video: str, start: float, duration: float, sample_rate: int = 16000) -> np.ndarray:
    proc = subprocess.run(
        [
            FFMPEG, "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.05, duration):.3f}",
            "-i", str(video), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-",
        ],
        capture_output=True, creationflags=_NO_WINDOW, timeout=120,
    )
    if proc.returncode != 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def audio_features(video: str, start: float, duration: float) -> dict[str, float]:
    pcm = _ffmpeg_pcm(video, start, duration)
    if pcm.size == 0:
        return {"activity": 0.0, "peak": 0.0, "rms": 0.0, "silence_ratio": 1.0, "speech_like": 0.0}
    window = max(1, int(0.05 * 16000))
    usable = pcm[: (pcm.size // window) * window]
    frames = usable.reshape(-1, window) if usable.size else pcm.reshape(1, -1)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    peak = float(np.max(np.abs(pcm)))
    floor = float(np.percentile(rms, 20))
    threshold = max(0.006, floor * 2.5, peak * 0.03)
    active = float(np.mean(rms > threshold))
    silence = float(np.mean(rms <= threshold))
    speech_like = 1.0 if active >= 0.12 and peak >= 0.02 else 0.0
    return {
        "activity": round(active, 4),
        "peak": round(peak, 4),
        "rms": round(float(np.mean(rms)), 4),
        "silence_ratio": round(silence, 4),
        "speech_like": speech_like,
    }


def _mp():
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/adplus-mpl")
    import mediapipe as mp

    return mp


def _face_detector():
    mp = _mp()
    return mp.tasks.vision.FaceDetector.create_from_options(
        mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(FACE_MODEL)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=0.3,
        )
    )


def face_features(video: str, start: float, duration: float, sample_fps: float = 5.0) -> dict[str, Any]:
    """Return face visibility and a lower-face motion proxy for one shot.

    We intentionally do not depend on FaceLandmarker here: on real ad frames a
    turned/small face often fails landmarking while the detector still finds
    it.  Lower-face frame difference is a robust proxy for "is the mouth/jaw
    moving", and is correlated with audio energy by the caller.
    """
    if not FACE_MODEL.is_file():
        return {"available": False, "face_visible": None, "mouth_motion": 0.0, "mouth_series": [], "times": []}
    try:
        import cv2

        mp = _mp()
        detector = _face_detector()
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(fps / max(0.5, sample_fps))))
        total = int(duration * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
        times: list[float] = []
        motions: list[float] = []
        detected = 0
        sampled = 0
        previous = None
        for index in range(max(1, total // step)):
            ok, frame = cap.read()
            if not ok:
                break
            if index > 0 and step > 1:
                for _ in range(step - 1):
                    cap.grab()
            sampled += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = detector.detect(image)
            if not result.detections:
                times.append(start + index * step / fps)
                motions.append(0.0)
                previous = None
                continue
            detected += 1
            box = max(result.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height).bounding_box
            x0 = max(0, box.origin_x + int(box.width * 0.18))
            x1 = min(frame.shape[1], box.origin_x + int(box.width * 0.82))
            y0 = max(0, box.origin_y + int(box.height * 0.52))
            y1 = min(frame.shape[0], box.origin_y + box.height)
            crop = rgb[y0:y1, x0:x1]
            if crop.size == 0:
                motions.append(0.0)
                previous = None
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            gray = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
            if previous is not None:
                motions.append(float(np.mean(np.abs(gray.astype(np.float32) - previous)) / 255.0))
            else:
                motions.append(0.0)
            previous = gray.astype(np.float32)
            times.append(start + index * step / fps)
        cap.release()
        detector.close()
        if not sampled:
            return {"available": True, "face_visible": False, "mouth_motion": 0.0, "mouth_series": [], "times": []}
        arr = np.asarray(motions, dtype=np.float32)
        visible = detected / max(1, sampled) >= 0.2
        return {
            "available": True,
            "face_visible": bool(visible),
            "face_ratio": round(detected / max(1, sampled), 3),
            "mouth_motion": round(float(np.mean(arr)) if arr.size else 0.0, 5),
            "mouth_series": [round(float(x), 4) for x in arr.tolist()],
            "times": [round(float(x), 3) for x in times],
        }
    except Exception as exc:  # noqa: BLE001 - analysis must not crash
        return {"available": False, "error": str(exc)[:160], "face_visible": None, "mouth_motion": 0.0, "mouth_series": [], "times": []}


def _corr(a: Iterable[float], b: Iterable[float]) -> float:
    x = np.asarray(list(a), dtype=np.float32)
    y = np.asarray(list(b), dtype=np.float32)
    if x.size < 3 or y.size != x.size or x.std() < 1e-6 or y.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def classify(
    audio: dict[str, float],
    face: dict[str, Any],
    *,
    mouth_threshold: float = 0.008,
) -> dict[str, Any]:
    speech = bool(audio.get("speech_like"))
    visible = face.get("face_visible")
    mouth = float(face.get("mouth_motion") or 0.0)
    face_ratio = float(face.get("face_ratio") or 0.0)
    if not speech:
        mode, confidence = "no_speech", 0.9
    elif visible is False:
        mode, confidence = "voiceover", 0.85
    elif visible is True and face_ratio < 0.5:
        mode, confidence = "unknown", 0.45
    elif visible is True and mouth >= mouth_threshold:
        mode, confidence = "on_camera", 0.65
    elif visible is True:
        mode, confidence = "voiceover", 0.6
    else:
        mode, confidence = "unknown", 0.3
    return {
        "mode": mode,
        "confidence": confidence,
        "face_visible": visible,
        "mouth_motion": round(mouth, 5),
        "audio_activity": audio.get("activity", 0.0),
    }


def analyze_shot(video: str, start: float, duration: float) -> dict[str, Any]:
    audio = audio_features(video, start, duration)
    face = face_features(video, start, duration)
    result = classify(audio, face)
    result["audio"] = audio
    result["face_ratio"] = face.get("face_ratio")
    return result


def analyze_shots(video: str, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for shot in shots:
        start = float(shot.get("start_s") or 0.0)
        duration = float(shot.get("duration_s") or max(0.2, float(shot.get("end_s") or start) - start))
        row = analyze_shot(video, start, duration)
        row["shot_id"] = shot.get("id")
        results.append(row)
    return results
