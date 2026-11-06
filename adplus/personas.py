"""Reusable digital presenters ("数字模特") for Ad+.

A persona is not a project asset.  It is a long-lived, rights-aware record of
a presenter that any project can reference:

    personas/<id>.json
    personas/<id>.md          (optional notes, not required)

Keeping it outside ``projects/`` means a model does not have to be re-uploaded
for every ad, and a rights decision is made once.  Source media stays in the
normal uploads/assets store; the persona record only stores workspace-relative
paths so it can be served by /api/media.

Schema is intentionally small and additive.  Provider-specific ids (HeyGen
avatar id, Kling face id, ...) live under ``providers`` so adding a new vendor
does not require a new top-level field.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from adplus.paths import PERSONAS

PERSONA_KINDS = ("photo", "video", "avatar")
PERSONA_STATUSES = ("draft", "ready", "archived")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _check_id(value: str) -> str:
    value = (value or "").strip()
    if not _ID_RE.match(value):
        raise ValueError(f"persona id must match {_ID_RE.pattern}")
    return value


def _read(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _dir(create: bool = False) -> Path:
    if create:
        PERSONAS.mkdir(parents=True, exist_ok=True)
    return PERSONAS


def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    persona = copy.deepcopy(data)
    persona.setdefault("id", f"p_{uuid.uuid4().hex[:8]}")
    persona["name"] = str(persona.get("name") or "").strip()
    kind = str(persona.get("kind") or "photo")
    persona["kind"] = kind if kind in PERSONA_KINDS else "photo"
    status = str(persona.get("status") or "draft")
    persona["status"] = status if status in PERSONA_STATUSES else "draft"
    persona.setdefault("source_path", None)
    persona.setdefault("preview_path", None)
    persona["asset_paths"] = [str(p) for p in (persona.get("asset_paths") or []) if str(p).strip()]
    persona["tags"] = [str(t) for t in (persona.get("tags") or []) if str(t).strip()]
    persona.setdefault("description", "")
    persona.setdefault("gender", "")
    persona.setdefault("age_range", "")
    persona.setdefault("look", "")
    persona.setdefault("wardrobe", "")
    persona.setdefault("scene", "")
    voice = persona.get("voice") if isinstance(persona.get("voice"), dict) else {}
    persona["voice"] = voice
    rights = persona.get("rights") if isinstance(persona.get("rights"), dict) else {}
    persona["rights"] = {
        "ai_allowed": bool(rights.get("ai_allowed")),
        "consent": bool(rights.get("consent")),
        "commercial_use": bool(rights.get("commercial_use")),
        "note": str(rights.get("note") or ""),
        "expires_at": str(rights.get("expires_at") or ""),
    }
    providers = persona.get("providers") if isinstance(persona.get("providers"), dict) else {}
    persona["providers"] = {
        str(k): str(v) for k, v in providers.items() if v is not None and str(v).strip()
    }
    persona.setdefault("created_at", _now())
    persona.setdefault("updated_at", persona["created_at"])
    return persona


def list_personas(include_archived: bool = False) -> list[dict[str, Any]]:
    directory = _dir()
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        persona = _read(path)
        if not persona:
            continue
        if not include_archived and persona.get("status") == "archived":
            continue
        rows.append(_normalise(persona))
    rows.sort(key=lambda p: str(p.get("updated_at") or ""), reverse=True)
    return rows


def load_persona(persona_id: str) -> dict[str, Any] | None:
    data = _read(_dir() / f"{_check_id(persona_id)}.json")
    return _normalise(data) if data else None


def save_persona(data: dict[str, Any], persona_id: str | None = None) -> dict[str, Any]:
    if not persona_id and data.get("id"):
        persona_id = _check_id(str(data["id"]))
    existing = load_persona(persona_id) if persona_id else None
    persona = _normalise({**(existing or {}), **copy.deepcopy(data)})
    if persona_id:
        persona["id"] = _check_id(persona_id)
    else:
        persona["id"] = f"p_{uuid.uuid4().hex[:8]}"
    if not persona["name"]:
        raise ValueError("persona name required")
    if persona["kind"] == "photo" and not (persona.get("source_path") or persona.get("preview_path")):
        raise ValueError("photo persona needs source_path or preview_path")
    persona["updated_at"] = _now()
    _atomic(_dir(create=True) / f"{persona['id']}.json", persona)
    return persona


def delete_persona(persona_id: str) -> bool:
    path = _dir() / f"{_check_id(persona_id)}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def persona_snapshot(persona_id: str | None) -> dict[str, Any] | None:
    if not persona_id:
        return None
    persona = load_persona(persona_id)
    if persona is None:
        return None
    snapshot = copy.deepcopy(persona)
    snapshot["captured_at"] = _now()
    return snapshot
