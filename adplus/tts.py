"""Local TTS fallback for the assets stage.

Provider TTS is preferred when configured.  This module only supplies a
deterministic local voice on macOS so an avatar shot is not permanently blocked
by a missing cloud key.  It is not a voice-clone provider.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

VOICE_ALIASES = {
    "tingting": "Tingting",
    "婷婷": "Tingting",
    "meijia": "Meijia",
    "美佳": "Meijia",
    "samantha": "Samantha",
    "daniel": "Daniel",
}


def available() -> bool:
    return shutil.which("say") is not None and shutil.which("ffmpeg") is not None


def _voice(value: str, language: str = "zh-CN") -> str:
    raw = (value or "").strip()
    if raw.lower() in VOICE_ALIASES:
        return VOICE_ALIASES[raw.lower()]
    if raw:
        return raw
    return "Tingting" if str(language).lower().startswith("zh") else "Samantha"


def synthesize(
    text: str,
    output_path: str | Path,
    *,
    voice: str = "Tingting",
    language: str = "zh-CN",
    speed: float = 1.0,
) -> dict[str, Any]:
    """Generate a 16 kHz mono WAV from text using macOS `say`."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        raise ValueError("TTS text is empty")
    if not available():
        raise RuntimeError("local TTS unavailable; configure a TTS provider or install macOS say + ffmpeg")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    aiff = output.with_suffix(".aiff")
    rate = max(120, min(260, int(180 * max(0.5, min(2.0, float(speed or 1.0))))))
    try:
        subprocess.run(
            ["say", "-v", _voice(voice, language), "-r", str(rate), "-o", str(aiff), clean],
            check=True, capture_output=True, timeout=180,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(output)],
            check=True, capture_output=True, timeout=60,
        )
        return {"path": str(output), "voice": _voice(voice, language), "bytes": output.stat().st_size, "provider": "local"}
    finally:
        aiff.unlink(missing_ok=True)
