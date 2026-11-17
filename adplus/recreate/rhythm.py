"""Rhythm analysis: energy, pauses, onsets, tempo, cut density, camera motion.

No librosa/scipy.  The two things the product actually needs are (a) where the
delivery speeds up and (b) how the picture moves, so this module stays on
numpy + OpenCV, both already installed.  Values are deliberately coarse —
they feed labels and heuristics, not a music-information-retrieval benchmark.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from adplus.recreate import media

FRAME_MS = 20
HOP_MS = 10
SILENCE_REL_DB = -28.0
MIN_SILENCE_S = 0.25


def analyze_audio(audio: np.ndarray, sample_rate: int = 16000) -> dict[str, Any]:
    if audio.size == 0:
        return {"error": "empty audio"}
    frame = int(sample_rate * FRAME_MS / 1000)
    hop = int(sample_rate * HOP_MS / 1000)
    rms = _rms(audio, frame, hop)
    db = 20.0 * np.log10(np.maximum(rms, 1e-8))
    floor = float(np.percentile(db, 10))
    speech = db > (floor + 12.0)

    flux = _spectral_flux(audio, sample_rate, 512, hop)
    onsets = _pick_onsets(flux, hop / sample_rate)
    tempo = _tempo(flux, hop / sample_rate)

    return {
        "hop_s": round(hop / sample_rate, 4),
        "db": {"floor": round(floor, 1), "peak": round(float(db.max()), 1), "mean": round(float(db.mean()), 1)},
        "energy_curve": [round(float(v), 1) for v in db[::max(1, len(db) // 240)]],
        "speech_ratio": round(float(speech.mean()), 3),
        "silences": _silences(speech, hop / sample_rate),
        "onsets": {"count": len(onsets), "per_s": round(len(onsets) / max(0.5, audio.size / sample_rate), 2)},
        "tempo_bpm": tempo["bpm"],
        "tempo_confidence": tempo["confidence"],
    }


def _rms(audio: np.ndarray, frame: int, hop: int) -> np.ndarray:
    count = max(1, 1 + (audio.size - frame) // hop)
    values = np.empty(count, dtype=np.float64)
    for i in range(count):
        chunk = audio[i * hop: i * hop + frame]
        values[i] = np.sqrt(np.mean(chunk.astype(np.float64) ** 2)) if chunk.size else 0.0
    return values


def _spectral_flux(audio: np.ndarray, sr: int, n_fft: int, hop: int) -> np.ndarray:
    window = np.hanning(n_fft)
    count = max(1, 1 + (audio.size - n_fft) // hop)
    previous = None
    flux = np.zeros(count, dtype=np.float64)
    for i in range(count):
        chunk = audio[i * hop: i * hop + n_fft]
        if chunk.size < n_fft:
            break
        magnitude = np.abs(np.fft.rfft(chunk * window))
        if previous is not None:
            diff = magnitude - previous
            flux[i] = float(np.sum(diff[diff > 0]))
        previous = magnitude
    return flux


def _pick_onsets(flux: np.ndarray, hop_s: float) -> list[float]:
    if flux.size < 8:
        return []
    smooth = np.convolve(flux, np.ones(5) / 5, mode="same")
    local = np.convolve(smooth, np.ones(31) / 31, mode="same")
    threshold = local * 1.5 + 1e-6
    hits: list[float] = []
    last = -1.0
    for i in range(1, flux.size - 1):
        if smooth[i] > threshold[i] and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            t = i * hop_s
            if t - last >= 0.12:
                hits.append(round(t, 3))
                last = t
    return hits


def _tempo(flux: np.ndarray, hop_s: float) -> dict[str, Any]:
    if flux.size < 40:
        return {"bpm": None, "confidence": 0.0}
    signal = flux - flux.mean()
    corr = np.correlate(signal, signal, mode="full")[signal.size - 1:]
    if corr[0] <= 0:
        return {"bpm": None, "confidence": 0.0}
    corr = corr / corr[0]
    lo = int((60 / 200) / hop_s)   # 200 BPM
    hi = int((60 / 50) / hop_s)    # 50 BPM
    band = corr[lo:hi]
    if band.size == 0:
        return {"bpm": None, "confidence": 0.0}
    idx = int(np.argmax(band))
    peak = float(band[idx])
    return {"bpm": round(60.0 / ((idx + lo) * hop_s), 1), "confidence": round(max(0.0, peak), 2)}


def _silences(speech: np.ndarray, hop_s: float) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    start = None
    for i, voiced in enumerate(speech):
        if not voiced and start is None:
            start = i
        elif voiced and start is not None:
            length = (i - start) * hop_s
            if length >= MIN_SILENCE_S:
                out.append({"start": round(start * hop_s, 2), "end": round(i * hop_s, 2), "len": round(length, 2)})
            start = None
    if start is not None:
        length = (len(speech) - start) * hop_s
        if length >= MIN_SILENCE_S:
            out.append({"start": round(start * hop_s, 2), "end": round(len(speech) * hop_s, 2), "len": round(length, 2)})
    return out


def analyze_motion(path: str | Path, shots: list[tuple[float, float]]) -> dict[str, Any]:
    """Mean optical-flow magnitude per shot, normalised to the frame diagonal."""
    try:
        import cv2
    except ImportError:
        return {"error": "opencv missing", "per_shot": []}

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"error": "cannot open video", "per_shot": []}

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    result: list[dict[str, Any]] = []
    try:
        for start, end in shots:
            frames: list[np.ndarray] = []
            t = start + 0.05
            while t < end - 0.05 and len(frames) < 24:
                capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = capture.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (160, max(1, int(gray.shape[0] * 160 / max(1, gray.shape[1])))))
                frames.append(gray)
                t += 0.25
            magnitudes = []
            for a, b in zip(frames, frames[1:]):
                flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                magnitudes.append(float(magnitude.mean()))
            mean = float(np.mean(magnitudes)) if magnitudes else 0.0
            # Normalised by frame width so the label does not depend on the
            # 160px analysis size: ~0.005 is a locked-off shot, >0.02 is walking.
            norm = mean / 160.0
            result.append(
                {
                    "start": start,
                    "end": end,
                    "mean_flow": round(mean, 3),
                    "flow_norm": round(norm, 4),
                    "level": "static" if norm < 0.005 else ("slow" if norm < 0.02 else "fast"),
                }
            )
    finally:
        capture.release()
    overall = float(np.mean([r["flow_norm"] for r in result])) if result else 0.0
    return {"per_shot": result, "mean_flow_norm": round(overall, 4)}
