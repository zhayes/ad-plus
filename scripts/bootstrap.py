#!/usr/bin/env python3
"""First-run dependency bootstrap for the Ad+ desktop app.

Runs with the *system* python3 (3.9 is enough — stdlib only), installs what the
app needs, and writes progress to:

    ~/Library/Application Support/Ad+/bootstrap.json   (read by the shell)
    ~/Library/Application Support/Ad+/bootstrap.log    (full command output)

Idempotent: every step checks first, so re-running after a failure resumes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE = Path(os.environ.get("ADPLUS_HOME") or Path(__file__).resolve().parent.parent)
VENDOR = WORKSPACE / "vendor" / "openmontage"
APP_DATA = Path.home() / "Library" / "Application Support" / "Ad+"
STATUS = APP_DATA / "bootstrap.json"
LOG = APP_DATA / "bootstrap.log"

STEPS = [
    ("python", "Python 3.10+"),
    ("venv", "创建虚拟环境"),
    ("deps", "安装 Python 依赖"),
    ("node", "Node.js 18+"),
    ("remotion", "渲染器（Remotion）"),
    ("pi", "agent 运行时（Pi）"),
    ("ffmpeg", "ffmpeg"),
]


def say(line: str) -> None:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H:%M:%S")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {line}\n")
    print(line, flush=True)


def write_status(step: str, state: str, detail: str = "", ok: bool = False) -> None:
    steps = []
    for sid, label in STEPS:
        if sid == step:
            steps.append({"id": sid, "label": label, "state": state, "detail": detail})
        else:
            steps.append({"id": sid, "label": label, "state": "pending", "detail": ""})
    payload = {
        "ok": ok,
        "step": step,
        "state": state,
        "detail": detail,
        "steps": steps,
        "updated": int(time.time()),
        "log": str(LOG),
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(cmd: list, cwd: Path | None = None, env: dict | None = None) -> tuple:
    say("$ " + " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd or WORKSPACE),
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.strip().splitlines()[-40:]:
        say("  " + line)
    return proc.returncode, out


def version_of(python: Path) -> tuple:
    try:
        proc = subprocess.run(
            [str(python), "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True, timeout=10,
        )
        parts = proc.stdout.strip().split(".")
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return (0, 0, 0)


def find_python() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("ADPLUS_PYTHON")
    if env and Path(env).exists():
        candidates.append(Path(env))
    for root in ("~/.pyenv/versions", "/opt/homebrew/opt", "/usr/local/opt"):
        base = Path(root).expanduser()
        if base.is_dir():
            for child in sorted(base.iterdir(), reverse=True):
                for name in ("bin/python3", "bin/python3.14", "bin/python3.13", "bin/python3.12", "bin/python3.11", "bin/python3.10"):
                    cand = child / name
                    if cand.exists():
                        candidates.append(cand)
    for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    seen = set()
    for cand in candidates:
        real = str(cand.resolve()) if cand.exists() else str(cand)
        if real in seen:
            continue
        seen.add(real)
        if version_of(cand) >= (3, 10):
            return cand
    return None


def brew_install(pkg: str) -> bool:
    brew = shutil.which("brew")
    if not brew:
        return False
    code, _ = run([brew, "install", pkg])
    return code == 0


def ensure_python() -> Path:
    write_status("python", "running", "查找 Python 3.10+")
    python = find_python()
    if python:
        write_status("python", "done", str(python), ok=False)
        return python
    say("没有找到 3.10+ 的解释器，尝试 Homebrew 安装")
    write_status("python", "running", "brew install python@3.14")
    if not brew_install("python@3.14"):
        raise RuntimeError("需要 Python 3.10+：请安装 https://www.python.org/downloads/ 后重试")
    python = find_python()
    if not python:
        raise RuntimeError("Homebrew 安装完成但没找到解释器，请重开应用")
    write_status("python", "done", str(python))
    return python


def ensure_venv(python: Path) -> Path:
    venv = WORKSPACE / ".venv"
    write_status("venv", "running", "")
    current = venv / "bin" / "python"
    if current.exists() and version_of(current) >= (3, 10):
        write_status("venv", "done", f"{version_of(current)}")
        return venv
    if venv.exists():
        say("旧虚拟环境版本过低，重建")
        shutil.rmtree(venv)
    code, _ = run([python, "-m", "venv", venv])
    if code != 0:
        raise RuntimeError("创建虚拟环境失败")
    write_status("venv", "done", str(version_of(venv / "bin" / "python")))
    return venv


def requirements_hash() -> str:
    digest = hashlib.sha1()
    for path in (VENDOR / "requirements.txt", WORKSPACE / "requirements-adplus.txt"):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def ensure_deps(venv: Path) -> None:
    write_status("deps", "running", "")
    marker = venv / ".adplus-deps"
    stamp = requirements_hash()
    if marker.is_file() and marker.read_text().strip() == stamp:
        write_status("deps", "done", "已是最新")
        return
    pip = venv / "bin" / "pip"
    run([pip, "install", "-q", "--upgrade", "pip"])
    code, out = run([
        pip, "install", "-q",
        "-r", VENDOR / "requirements.txt",
        "-r", WORKSPACE / "requirements-adplus.txt",
    ])
    if code != 0:
        raise RuntimeError("pip 安装失败，详见日志")
    marker.write_text(stamp)
    write_status("deps", "done", "")


def ensure_node() -> None:
    write_status("node", "running", "")
    node = shutil.which("node")
    if node:
        try:
            proc = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=10)
            major = int(re.sub(r"[^0-9]", "", proc.stdout.strip().split(".")[0]) or 0)
            if major >= 18:
                write_status("node", "done", proc.stdout.strip())
                return
        except Exception:
            pass
    if not brew_install("node"):
        raise RuntimeError("需要 Node.js 18+：https://nodejs.org/")
    write_status("node", "done", "brew")


def ensure_remotion() -> None:
    write_status("remotion", "running", "")
    composer = VENDOR / "remotion-composer"
    if (composer / "node_modules").is_dir():
        write_status("remotion", "done", "已安装")
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("找不到 npm（Node 未安装？）")
    code, _ = run([npm, "install", "--no-audit", "--no-fund"], cwd=composer)
    if code != 0:
        raise RuntimeError("Remotion 依赖安装失败，详见日志")
    write_status("remotion", "done", "")


def ensure_pi() -> None:
    write_status("pi", "running", "")
    if shutil.which("pi"):
        write_status("pi", "done", shutil.which("pi") or "pi")
        return
    local = Path.home() / ".local" / "bin" / "pi"
    if local.exists():
        write_status("pi", "done", str(local))
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("找不到 npm，无法安装 Pi")
    env = dict(os.environ)
    env["npm_config_prefix"] = str(Path.home() / ".local")
    code, _ = run([npm, "install", "-g", "--no-audit", "--no-fund",
                   "@earendil-works/pi-coding-agent@1.5.0"], env=env)
    if code != 0 or not local.exists():
        raise RuntimeError("Pi 安装失败，详见日志")
    write_status("pi", "done", str(local))


def ensure_ffmpeg() -> None:
    write_status("ffmpeg", "running", "")
    if shutil.which("ffmpeg"):
        write_status("ffmpeg", "done", shutil.which("ffmpeg") or "")
        return
    if brew_install("ffmpeg"):
        write_status("ffmpeg", "done", "brew")
        return
    raise RuntimeError("需要 ffmpeg：brew install ffmpeg")


def main() -> int:
    if "--status" in sys.argv:
        if STATUS.is_file():
            print(STATUS.read_text(encoding="utf-8"))
            return 0
        print(json.dumps({"ok": False, "state": "missing"}))
        return 0

    APP_DATA.mkdir(parents=True, exist_ok=True)
    say("=== Ad+ bootstrap ===")
    say("workspace: %s" % WORKSPACE)
    try:
        python = ensure_python()
        venv = ensure_venv(python)
        ensure_deps(venv)
        ensure_node()
        ensure_remotion()
        ensure_pi()
        ensure_ffmpeg()
    except Exception as exc:  # noqa: BLE001 - the UI shows this message
        say("FAILED: %s" % exc)
        payload = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.is_file() else {"steps": []}
        payload.update({"ok": False, "state": "failed", "detail": str(exc),
                        "updated": int(time.time()), "log": str(LOG)})
        STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    steps = [{"id": sid, "label": label, "state": "done", "detail": ""} for sid, label in STEPS]
    STATUS.write_text(json.dumps({
        "ok": True, "step": "done", "state": "done", "detail": "",
        "steps": steps, "updated": int(time.time()), "log": str(LOG),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    say("=== ready ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
