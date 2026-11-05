"""Secret storage for the desktop app.

Source of truth is the macOS Keychain (one generic-password item per key,
service ``openmontage``). A 0600 JSON mirror is written next to the app data
so child processes (``om_mcp``, tool subprocesses) can read keys without
touching the Keychain on every launch — the mirror is the runtime cache, the
Keychain is the durable copy.

Every failure path degrades to the file store instead of raising: a locked
Keychain must not take the app down, it should only downgrade the guarantee.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

SERVICE = "adplus"
LEGACY_SERVICE = "openmontage"
APP_DIR_NAME = "Ad+"


def app_data_dir() -> Path:
    override = os.environ.get("OPENMONTAGE_APP_DATA") or os.environ.get("ADPLUS_APP_DATA")
    if override:
        path = Path(override)
    else:
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if not path.exists():
        _migrate_legacy(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _migrate_legacy(target: Path) -> None:
    """Move a pre-rename "OpenMontage" profile over, once.

    Renaming the app must not orphan sessions, thumbnails or the secret
    mirror, so the old directory is moved rather than abandoned.
    """
    legacy = Path.home() / "Library" / "Application Support" / "OpenMontage"
    if not legacy.is_dir():
        return
    try:
        legacy.rename(target)
    except OSError:
        import shutil as _shutil

        _shutil.copytree(legacy, target, dirs_exist_ok=True)
    # Re-file any legacy Keychain entries under the new service name.
    mirror = target / "secrets.json"
    if mirror.is_file():
        import json as _json

        try:
            names = list(_json.loads(mirror.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            names = []
        for name in names:
            value = _keychain_get_legacy(name)
            if value:
                _keychain_set(name, value)


def mirror_path() -> Path:
    return app_data_dir() / "secrets.json"


def _security() -> str | None:
    return shutil.which("security")


def keychain_available() -> bool:
    return _security() is not None and os.uname().sysname == "Darwin"


def _keychain_set(name: str, value: str) -> bool:
    exe = _security()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "add-generic-password", "-a", name, "-s", SERVICE, "-w", value, "-U"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _keychain_get(name: str) -> str | None:
    exe = _security()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "find-generic-password", "-a", name, "-s", SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _keychain_get_legacy(name: str) -> str | None:
    exe = _security()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "find-generic-password", "-a", name, "-s", LEGACY_SERVICE, "-w"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def _keychain_delete(name: str) -> bool:
    exe = _security()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "delete-generic-password", "-a", name, "-s", SERVICE],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _read_mirror() -> dict[str, str]:
    path = mirror_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: str(v) for k, v in data.items() if k and v}


def _write_mirror(data: dict[str, str]) -> None:
    path = mirror_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def set_secret(name: str, value: str) -> dict[str, object]:
    value = (value or "").strip()
    if not value:
        raise ValueError("empty value")
    in_keychain = _keychain_set(name, value) if keychain_available() else False
    data = _read_mirror()
    data[name] = value
    _write_mirror(data)
    return {"name": name, "keychain": in_keychain, "stored": True}


def delete_secret(name: str) -> dict[str, object]:
    in_keychain = _keychain_delete(name) if keychain_available() else False
    data = _read_mirror()
    existed = data.pop(name, None) is not None
    _write_mirror(data)
    return {"name": name, "keychain_removed": in_keychain, "removed": existed}


def get_secret(name: str) -> str | None:
    value = _keychain_get(name) if keychain_available() else None
    if value:
        return value
    return _read_mirror().get(name)


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def configured_names() -> set[str]:
    names = set(_read_mirror())
    return names


def merged_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for child processes: caller env + stored secrets (stored wins)."""
    env = dict(base if base is not None else os.environ)
    env.update(_read_mirror())
    return env


def export_mirror_for_children(names: Iterable[str] | None = None) -> Path:
    """Rewrite the mirror from the Keychain so children see the latest values."""
    if keychain_available():
        data = _read_mirror()
        for name in list(data) if names is None else names:
            value = _keychain_get(name)
            if value:
                data[name] = value
        _write_mirror(data)
    return mirror_path()
