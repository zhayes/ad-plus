"""Environment helpers for processes launched from Finder.

A GUI launch has a minimal PATH (`/usr/bin:/bin:...`), so `pi`, `node`, `npx`
and `ffmpeg` are invisible even though they work in a terminal. Every child
process the app spawns must get this PATH prefix.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def node_bin_dirs() -> list[str]:
    dirs = [
        str(Path.home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.is_dir():
        dirs += [str(p / "bin") for p in sorted(nvm.iterdir(), reverse=True) if (p / "bin").is_dir()]
    return [d for d in dirs if Path(d).is_dir()]


def spawn_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """os.environ with a PATH that can actually find node/pi/npx/ffmpeg.

    `extra` is applied first: callers pass `secrets_store.merged_env()`, which
    is a copy of os.environ and would otherwise clobber the augmented PATH.
    """
    env = dict(os.environ)
    if extra:
        env.update(extra)
    current = env.get("PATH", os.environ.get("PATH", ""))
    prefix = node_bin_dirs()
    parts = [p for p in prefix if p not in current.split(":")]
    env["PATH"] = ":".join(parts + ([current] if current else []))
    return env


def find_node_tool(name: str) -> str | None:
    """Resolve a Node CLI (pi/npx) with the augmented PATH."""
    found = shutil.which(name, path=spawn_env()["PATH"])
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / name
    return str(candidate) if candidate.exists() else None
