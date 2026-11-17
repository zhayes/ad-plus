"""Chinese voiceover through MiniMax speech-02.

The provider returns hex-encoded audio inside JSON (not raw bytes), so the
helper writes the decoded file and returns its metadata.  Callers treat any
exception as "provider unavailable" and fall back to the local `say` voice.
"""

from __future__ import annotations

import binascii
import os
from pathlib import Path
from typing import Any

import requests

HOST = os.environ.get("MINIMAX_TTS_HOST", "https://api.minimaxi.com")
MODEL = os.environ.get("ADPLUS_TTS_MODEL", "speech-02-hd")
VOICE = os.environ.get("ADPLUS_TTS_VOICE", "male-qn-jingying")


def _key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "")
    if key:
        return key
    try:
        from app import secrets_store

        return secrets_store.merged_env().get("MINIMAX_API_KEY", "")
    except Exception:  # noqa: BLE001
        return ""


def synthesize(text: str, out: str | Path, *, voice: str | None = None, speed: float = 1.0, pitch: int = 0) -> dict[str, Any]:
    key = _key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY missing")
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")

    body = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice or VOICE,
            "speed": max(0.5, min(2.0, speed)),
            "vol": 1.0,
            "pitch": max(-12, min(12, int(pitch))),
        },
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    resp = requests.post(
        f"{HOST}/v1/t2a_v2",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    data = resp.json() if resp.content else {}
    audio = (data.get("data") or {}).get("audio")
    status = (data.get("base_resp") or {}).get("status_code")
    if not audio or status not in (0, None):
        message = (data.get("base_resp") or {}).get("status_msg") or resp.text[:160]
        raise RuntimeError(f"MiniMax TTS {status}: {message}")

    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = binascii.unhexlify(audio)
    target.write_bytes(payload)
    return {"path": str(target), "provider": "minimax", "voice": voice or VOICE, "bytes": len(payload)}
