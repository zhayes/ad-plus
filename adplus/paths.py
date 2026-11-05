"""Every path Ad+ needs, resolved once.

Layout:

    <workspace>/                 ← Ad+ repo (this)
      adplus/                    Ad+ code
      app/  frontend/            backend + UI
      vendor/openmontage/        upstream checkout (git submodule)
      projects/  uploads/        user data
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("ADPLUS_HOME") or Path(__file__).resolve().parent.parent)

VENDOR = Path(os.environ.get("OPENMONTAGE_HOME") or WORKSPACE / "vendor" / "openmontage")

COMPOSER = Path(os.environ.get("OPENMONTAGE_COMPOSER_DIR") or VENDOR / "remotion-composer")

PROJECTS = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or WORKSPACE / "projects")

UPLOADS = Path(os.environ.get("OPENMONTAGE_UPLOADS_DIR") or WORKSPACE / "uploads")

MUSIC_LIBRARY = Path(os.environ.get("OPENMONTAGE_MUSIC_DIR") or WORKSPACE / "music_library")

# Cross-project brand kits (P0). Kept outside projects/ so a brand can be
# shared by every ad that references it.
BRANDS = Path(os.environ.get("ADPLUS_BRANDS_DIR") or WORKSPACE / "brands")

PI_CONFIG = Path.home() / ".pi" / "agent" / "mcp.json"


def ensure_vendor() -> Path:
    """Fail loudly instead of a confusing ImportError three frames down."""
    if not (VENDOR / "pipeline_defs").is_dir():
        raise RuntimeError(
            f"upstream checkout missing at {VENDOR} — run: git submodule update --init"
        )
    return VENDOR
