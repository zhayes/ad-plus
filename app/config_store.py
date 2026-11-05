"""Small user-configurable settings (currently: where finished videos go)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app import secrets_store

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "projects"  # workspace/projects


def _path() -> Path:
    return secrets_store.app_data_dir() / "config.json"


def load() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(data: dict[str, Any]) -> dict[str, Any]:
    merged = {**load(), **data}
    _path().write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def output_dir() -> Path:
    configured = load().get("output_dir")
    if configured:
        candidate = Path(str(configured)).expanduser()
        if candidate.is_dir():
            return candidate
    return DEFAULT_OUTPUT_DIR


def apply_to_env() -> None:
    """Pipelines resolve their project root from this env var."""
    os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(output_dir())
