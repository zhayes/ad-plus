"""User-authored Agent Skills for Ad+.

A skill is a folder with ``SKILL.md`` in the standard Agent Skills layout:

    <app data>/skills/<name>/SKILL.md

Only skills created here are managed. The upstream OpenMontage skills under
``vendor/openmontage/skills`` are never read, moved or listed. Pi knows about
this folder because ``PiBridge`` appends ``--skill <dir>`` when it starts a
session, so the skills stay scoped to Ad+ instead of leaking into every other
Pi project on the machine.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from app import secrets_store

SKILLS_DIR = secrets_store.app_data_dir() / "skills"

# Skills that ship with the repo (versioned under adplus/skills/). They are
# copied into the user dir only when missing, so editing one in the UI does
# not get clobbered on the next launch.
BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "adplus" / "skills"
TRASH_DIR_NAME = ".trash"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024


def _root(create: bool = False) -> Path:
    if create:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return SKILLS_DIR


def _skill_dir_for_slug(slug: str) -> Path:
    value = str(slug or "").strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value or value.startswith("."):
        raise ValueError("无效的技能目录")
    path = _root() / value
    if path.is_symlink():
        raise ValueError("技能目录不能是符号链接")
    return path


def _check_name(value: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("技能名不能为空")
    if len(name) > MAX_NAME:
        raise ValueError(f"技能名最多 {MAX_NAME} 个字符")
    if not NAME_RE.match(name):
        raise ValueError("技能名只能用小写字母、数字和连字符（例如 ad-hook）")
    return name


def _check_description(value: str) -> str:
    description = " ".join(str(value or "").split())
    if not description:
        raise ValueError("描述不能为空：模型靠它判断什么时候加载技能")
    if len(description) > MAX_DESCRIPTION:
        raise ValueError(f"描述最多 {MAX_DESCRIPTION} 个字符")
    return description


def _parse_skill_text(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not normalized.startswith("---"):
        return {}, normalized.strip()
    end = normalized.find("\n---", 3)
    if end == -1:
        return {}, normalized.strip()
    try:
        meta = yaml.safe_load(normalized[4:end]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, normalized[end + 4:].lstrip("\n").rstrip()


def _render_skill(name: str, description: str, instructions: str, extra: dict[str, Any]) -> str:
    meta = {key: value for key, value in (extra or {}).items() if key not in {"name", "description"}}
    meta["name"] = name
    meta["description"] = description
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    body = str(instructions or "").strip()
    return f"---\n{front}\n---\n\n{body}\n" if body else f"---\n{front}\n---\n"


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load(directory: Path) -> dict[str, Any] | None:
    file = directory / "SKILL.md"
    if not file.is_file():
        return None
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = _parse_skill_text(text)
    slug = directory.name
    name = str(meta.get("name") or slug).strip() or slug
    description = " ".join(str(meta.get("description") or "").split())
    errors: list[str] = []
    if not description:
        errors.append("缺少 description")
    if not NAME_RE.match(name):
        errors.append("name 只能用小写字母、数字和连字符")
    try:
        updated_at = time.strftime("%Y-%m-%d %H:%M", time.localtime(file.stat().st_mtime))
    except OSError:
        updated_at = ""
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "instructions": body,
        "path": str(file),
        "updated_at": updated_at,
        "valid": not errors,
        "error": "；".join(errors),
        "extra": {key: value for key, value in meta.items() if key not in {"name", "description"}},
    }


def _public(skill: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in skill.items() if key != "extra"}


def seed_builtin_skills() -> int:
    """Copy repo-shipped skills into the user skills dir when missing."""
    if not BUILTIN_SKILLS_DIR.is_dir():
        return 0
    root = _root(create=True)
    copied = 0
    for source in sorted(BUILTIN_SKILLS_DIR.iterdir()):
        if not source.is_dir() or source.is_symlink() or not (source / "SKILL.md").is_file():
            continue
        target = root / source.name
        if target.exists():
            continue
        try:
            shutil.copytree(source, target)
            copied += 1
        except OSError:
            continue
    return copied


def list_skills() -> list[dict[str, Any]]:
    seed_builtin_skills()
    root = _root(create=True)
    try:
        children = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for child in children:
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        row = _load(child)
        if row is not None:
            rows.append(_public(row))
    rows.sort(key=lambda row: str(row["name"]).lower())
    return rows


def save_skill(
    *,
    name: str | None = None,
    description: str | None = None,
    instructions: str | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    _root(create=True)
    if slug is not None:
        source = _skill_dir_for_slug(slug)
        current = _load(source)
        if current is None:
            raise FileNotFoundError(slug)
        final_name = _check_name(name if name is not None else current["name"])
        final_description = _check_description(
            description if description is not None else current["description"]
        )
        final_instructions = current["instructions"] if instructions is None else str(instructions)
        extra = current["extra"]
        target = _root() / final_name
        if target != source:
            if target.exists():
                raise FileExistsError(final_name)
            os.replace(source, target)
    else:
        if name is None or description is None:
            raise ValueError("name and description are required")
        final_name = _check_name(name)
        final_description = _check_description(description)
        final_instructions = str(instructions or "")
        extra = {}
        target = _root() / final_name
        if target.exists():
            raise FileExistsError(final_name)
        target.mkdir(parents=True, exist_ok=False)

    _write_file(target / "SKILL.md", _render_skill(final_name, final_description, final_instructions, extra))
    row = _load(target)
    if row is None:
        raise OSError("技能写入失败")
    return _public(row)


def delete_skill(slug: str) -> bool:
    source = _skill_dir_for_slug(slug)
    if not source.is_dir():
        return False
    trash = _root(create=True) / TRASH_DIR_NAME
    trash.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = trash / f"{source.name}-{stamp}"
    index = 1
    while target.exists():
        target = trash / f"{source.name}-{stamp}-{index}"
        index += 1
    os.replace(source, target)
    return True


def pi_skill_args() -> list[str]:
    """Extra CLI args so Pi loads user skills; empty when there is nothing."""
    # shortcut: names are not checked against Pi's global skills; a duplicate
    # is shadowed by the earlier skill. Add a pre-scan if users hit this.
    seed_builtin_skills()
    root = SKILLS_DIR
    try:
        if not root.is_dir():
            return []
        has_skill = any(
            child.is_dir()
            and not child.is_symlink()
            and not child.name.startswith(".")
            and (child / "SKILL.md").is_file()
            for child in root.iterdir()
        )
    except OSError:
        return []
    return ["--skill", str(root.resolve())] if has_skill else []
