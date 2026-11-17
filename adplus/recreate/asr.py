"""Speech layer: transcript, word timing, and a cheap A/B speaker split.

The vendor ``transcriber`` tool calls ``faster_whisper.decode_audio``, which
goes through PyAV.  The installed PyAV renamed a keyword argument
(``metadata_errors``), so that path raises ``TypeError`` on this machine.  We
decode with ffmpeg instead and hand faster-whisper a numpy array — same model,
no PyAV dependency, and it also works on Windows where ffmpeg ships with the
app.

Speaker labels are a heuristic on purpose.  A two-person ad does not justify
pyannote's install size; median F0 per segment plus 1-D k-means is enough to
tell ``A`` from ``B`` and to flag segments where the guess is weak.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from adplus.recreate import media

DEFAULT_MODEL = os.environ.get("ADPLUS_ASR_MODEL", "base")


def _default_cache() -> Path:
    """Model cache: env override, else Ad+ state dir (never the home dotfile).

    Keeping it under ``ADPLUS_STATE_DIR`` means a packaged app ships models
    next to its own state instead of scattering gigabytes through ~/.cache.
    """
    explicit = os.environ.get("ADPLUS_ASR_CACHE")
    if explicit:
        return Path(explicit)
    try:
        from adplus.paths import STATE_DIR

        return STATE_DIR / "whisper"
    except Exception:  # noqa: BLE001 - standalone use must still work
        return Path.home() / ".adplus" / "whisper"


def transcribe(
    path: str | Path,
    *,
    model_size: str | None = None,
    language: str | None = None,
    download_root: str | Path | None = None,
    speaker_split: bool = True,
) -> dict[str, Any]:
    """Return ``{language, duration_s, segments[], speakers}``.

    ``segments`` carry ``start/end/text/chars/cps/speaker/f0`` so later stages
    never have to re-run the model just to know how fast a line is delivered.
    """
    from faster_whisper import WhisperModel

    audio = media.audio_f32(path, 16000)
    model = WhisperModel(
        model_size or DEFAULT_MODEL,
        device="cpu",
        compute_type="int8",
        download_root=str(download_root or _default_cache()),
    )
    raw_segments, info = model.transcribe(
        audio,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
        # Do NOT pass an initial_prompt here: it merges the opening lines into
        # one 16-second segment and destroys the beat grid.  Traditional ->
        # Simplified is handled after the fact instead.
    )

    segments: list[dict[str, Any]] = []
    for seg in raw_segments:
        text = _to_simplified((seg.text or "").strip())
        if not text:
            continue
        start, end = float(seg.start), float(seg.end)
        if seg.words:
            # Whisper's segment timestamps include the lead-in silence; word
            # timings are what the beat grid needs, otherwise a line lands in
            # the previous shot and the beat table lies.
            start = min(float(w.start) for w in seg.words)
            end = max(float(w.end) for w in seg.words)
        chars = _visible_chars(text)
        segments.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "chars": chars,
                "cps": round(chars / max(0.2, end - start), 2),
                "words": [
                    {
                        "word": w.word,
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                        "probability": round(float(w.probability), 3),
                    }
                    for w in (seg.words or [])
                ],
            }
        )

    word_probs = [w["probability"] for seg in segments for w in seg["words"]]
    avg_word_prob = round(sum(word_probs) / len(word_probs), 3) if word_probs else 0.0
    quality = _quality(segments, float(getattr(info, "language_probability", 0.0) or 0.0), avg_word_prob)

    speakers: dict[str, Any] = {"labels": [], "confidence": 0.0, "method": "none"}
    if speaker_split and len(segments) >= 2:
        speakers = _assign_speakers(segments, audio, 16000)

    return {
        "language": language or getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
        "duration_s": round(float(getattr(info, "duration", 0.0) or 0.0), 3),
        "segments": segments,
        "speakers": speakers,
        "quality": quality,
        "model": model_size or DEFAULT_MODEL,
    }


def _quality(segments: list[dict[str, Any]], lang_prob: float, avg_word_prob: float) -> dict[str, Any]:
    """Flag transcripts that are probably hallucinated music/noise.

    AI-generated or music-only soundtracks make whisper invent Chinese lines
    with confident-looking timestamps.  Low language probability plus low word
    probability is the cheapest signal that the "dialogue" is not dialogue.
    """
    if not segments:
        return {"status": "none", "lang_prob": round(lang_prob, 3), "avg_word_prob": avg_word_prob,
                "note": "没有检测到可转写的人声"}
    if lang_prob < 0.6 and avg_word_prob < 0.6:
        return {"status": "low", "lang_prob": round(lang_prob, 3), "avg_word_prob": avg_word_prob,
                "note": "人声置信度低，可能是音乐/音效被误识别，台词需人工核对"}
    return {"status": "ok", "lang_prob": round(lang_prob, 3), "avg_word_prob": avg_word_prob, "note": ""}


def _to_simplified(text: str) -> str:
    """Convert Traditional Chinese when ``opencc`` is installed.

    Whisper emits Traditional characters on some Mandarin clips.  opencc is a
    small pure-Python dependency, but the pipeline must still run without it,
    so a missing module is not an error.
    """
    if not text:
        return text
    try:
        import opencc  # type: ignore

        return opencc.OpenCC("t2s").convert(text)
    except Exception:  # noqa: BLE001
        return text


def _visible_chars(text: str) -> int:
    import re

    return len(re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE))


def _assign_speakers(segments: list[dict[str, Any]], audio: np.ndarray, sr: int) -> dict[str, Any]:
    """Label each segment A (lower pitch) or B (higher pitch)."""
    f0s: list[float | None] = []
    for seg in segments:
        chunk = audio[int(seg["start"] * sr): int(seg["end"] * sr)]
        f0 = _median_f0(chunk, sr)
        f0s.append(f0)
        seg["f0"] = round(f0, 1) if f0 else None

    voiced = [f for f in f0s if f]
    if len(voiced) < 2:
        return {"labels": ["A"] * len(segments), "confidence": 0.0, "method": "single"}

    low, high = _kmeans_1d(voiced)
    gap = abs(high - low) / max(1.0, (high + low) / 2)
    labels = []
    for f0 in f0s:
        if not f0:
            labels.append(None)
        else:
            labels.append("A" if abs(f0 - low) <= abs(f0 - high) else "B")
    # A missing pitch is most likely the previous speaker continuing.
    last = "A"
    for i, label in enumerate(labels):
        labels[i] = last = (label or last)
        segments[i]["speaker"] = labels[i]
    # Pitch separation alone over-trusts outliers: one excited line at 270 Hz
    # against five at 190 Hz would score 1.0.  Weight it by cluster balance so
    # a 5:1 split reads as "probably one voice plus one guest", not certainty.
    counts = [labels.count("A"), labels.count("B")]
    balance = min(counts) / max(counts) if max(counts) else 0.0
    turns = sum(1 for a, b in zip(labels, labels[1:]) if a != b)
    return {
        "labels": labels,
        "confidence": round(min(1.0, (gap / 0.35) * (0.35 + 0.65 * balance)), 2),
        "method": "f0-kmeans",
        "f0_cluster": [round(low, 1), round(high, 1)],
        "balance": round(balance, 2),
        "turns": turns,
    }


def _kmeans_1d(values: list[float], iterations: int = 25) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    if lo == hi:
        return lo, hi
    for _ in range(iterations):
        mid = (lo + hi) / 2
        left = [v for v in values if v <= mid] or [lo]
        right = [v for v in values if v > mid] or [hi]
        lo, hi = float(np.mean(left)), float(np.mean(right))
    return lo, hi


def _median_f0(chunk: np.ndarray, sr: int, fmin: float = 70.0, fmax: float = 350.0) -> float | None:
    """Autocorrelation pitch over 40 ms frames; median of voiced frames."""
    if chunk.size < sr * 0.12:
        return None
    frame, hop = int(sr * 0.04), int(sr * 0.02)
    lo_lag, hi_lag = int(sr / fmax), int(sr / fmin)
    peaks: list[float] = []
    for start in range(0, chunk.size - frame, hop):
        win = chunk[start: start + frame].astype(np.float64)
        energy = float(np.sqrt(np.mean(win ** 2)))
        if energy < 0.01:
            continue
        win = win - win.mean()
        win *= np.hanning(frame)
        corr = np.correlate(win, win, mode="full")[frame - 1:]
        if corr[0] <= 0:
            continue
        corr = corr / corr[0]
        band = corr[lo_lag:hi_lag]
        if band.size == 0:
            continue
        idx = int(np.argmax(band))
        if band[idx] < 0.3:
            continue
        peaks.append(sr / (idx + lo_lag))
    if len(peaks) < 3:
        return None
    return float(np.median(peaks))
