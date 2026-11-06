"""Wire optional local OpenMontage tools without hardcoding them in the UI."""

from __future__ import annotations

import os
from pathlib import Path

from adplus.paths import WORKSPACE


def ensure_wav2lip() -> dict[str, str] | None:
    root = WORKSPACE / "vendor" / "wav2lip"
    inference = root / "inference.py"
    checkpoint = root / "checkpoints" / "wav2lip_gan.pth"
    if not inference.is_file() or not checkpoint.is_file():
        return None
    os.environ.setdefault("WAV2LIP_PATH", str(root))
    venv_bin = WORKSPACE / ".venv-wav2lip" / "bin"
    if venv_bin.is_dir():
        path = os.environ.get("PATH", "")
        if str(venv_bin) not in path.split(":"):
            os.environ["PATH"] = str(venv_bin) + ":" + path
    return {"path": str(root), "checkpoint": str(checkpoint), "python": str(venv_bin / "python")}


def ensure_local_tools() -> dict[str, dict[str, str] | None]:
    return {"wav2lip": ensure_wav2lip()}
