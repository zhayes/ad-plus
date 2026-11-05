"""OpenMontage desktop app (MVP shell).

Hosts the local settings/chat backend in-process and shows it in a native
WebKit window. The backend is shell-agnostic: the same FastAPI app can be
opened in a browser (`--no-window`), embedded by pywebview today, or loaded
by a Tauri window later without touching the Python side.

    python -m app.main              # window
    python -m app.main --no-window  # server only (smoke tests)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn

from app import secrets_store
from app.settings_server import app as fastapi_app

from adplus.paths import PROJECTS as PROJECTS_DIR
from adplus.paths import VENDOR as VENDOR_DIR
from adplus.paths import WORKSPACE as REPO_ROOT


def ensure_pi_mcp_config(repo_root: Path | None = None) -> dict[str, Any]:
    """Make sure Pi knows how to reach this OpenMontage install.

    Idempotent, and additive: other servers in the user's mcp.json are left
    untouched. Points the stdio server at the app's secret mirror so keys
    entered in the UI reach the tools without writing a repo `.env`.
    """
    repo = Path(repo_root or REPO_ROOT)
    config_path = Path.home() / ".pi" / "agent" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"mcpServers": {}}
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8")) or {"mcpServers": {}}
        except json.JSONDecodeError:
            data = {"mcpServers": {}}
    servers = data.setdefault("mcpServers", {})
    python = repo / ".venv" / "bin" / "python"
    servers["openmontage"] = {
        "command": str(python) if python.exists() else "python3",
        "args": ["-m", "adplus.mcp"],
        "cwd": str(repo),
        "env": {
            "OPENMONTAGE_SECRETS_FILE": str(secrets_store.mirror_path()),
            "PYTHONPATH": str(repo),
            "OPENMONTAGE_HOME": str(VENDOR_DIR),
            "OPENMONTAGE_PROJECTS_DIR": str(PROJECTS_DIR),
            "ADPLUS_HOME": str(repo),
        },
        "description": "OpenMontage video production: capabilities, projects, media generation, compose",
        "exposure": "direct",
        "timeout": 900,
    }
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"config": str(config_path), "server": "openmontage"}


def existing_backend(port: int) -> bool:
    """True when an OpenMontage backend already answers on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    return bool(payload.get("ok"))


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return sock.getsockname()[1]
    raise RuntimeError("no free port")


def start_backend(port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="om-backend", daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.2)
    return server, thread


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seconds", type=float, default=0, help="auto-close after N seconds (smoke test)")
    parser.add_argument("--parent-pid", type=int, default=0, help="exit when this process disappears (shell death)")
    args = parser.parse_args()

    ensure_pi_mcp_config()

    if args.parent_pid:
        def _watch_parent(pid: int) -> None:
            while True:
                time.sleep(2)
                try:
                    os.kill(pid, 0)
                except OSError:
                    os._exit(0)

        threading.Thread(target=_watch_parent, args=(args.parent_pid,), name="parent-watchdog", daemon=True).start()

    reuse = existing_backend(args.port)
    if reuse:
        port = args.port
        server = thread = None
        url = f"http://127.0.0.1:{port}/"
    else:
        port = _free_port(args.port)
        server, thread = start_backend(port)
        url = f"http://127.0.0.1:{port}/"
    print(f"Ad+ backend: {url}{' (reused)' if reuse else ''}", flush=True)

    if args.no_window:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=5)
        return 0

    import webview

    window = webview.create_window(
        "OpenMontage",
        url,
        width=1180,
        height=840,
        min_size=(960, 680),
        background_color="#0d0f14",
    )

    if args.seconds:
        def _close_later() -> None:
            time.sleep(args.seconds)
            try:
                window.destroy()
            except Exception:
                pass

        threading.Thread(target=_close_later, daemon=True).start()

    try:
        webview.start()
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
