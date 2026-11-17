"""Build the Ad+ Python backend as a PyInstaller onedir sidecar.

Windows is the primary target; run this inside a Python 3.12 venv:

    pip install -r vendor/openmontage/requirements.txt -r requirements-adplus.txt -r requirements-restyle.txt
    pip install pyinstaller
    python scripts/build_backend.py

Output:
    app/desktop/binaries/backend/adplus-backend/adplus-backend.exe
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "openmontage"
OUT = ROOT / "app" / "desktop" / "binaries" / "backend"
RESOURCES = ROOT / "app" / "desktop" / "resources"
BUILD = ROOT / "build"


def copy_vendor_data() -> None:
    target = RESOURCES / "vendor" / "openmontage"
    for name in ("pipeline_defs", "schemas", "skills", "styles"):
        source = VENDOR / name
        if source.is_dir():
            shutil.copytree(source, target / name, dirs_exist_ok=True)


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller is not installed. Run: pip install pyinstaller", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    args = [
        str(ROOT / "scripts" / "backend_entry.py"),
        "--name", "adplus-backend",
        "--onedir",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--log-level", "WARN",
        "--distpath", str(OUT),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--paths", str(VENDOR),
        "--collect-submodules", "app",
        "--collect-submodules", "adplus",
        "--collect-submodules", "lib",
        "--collect-submodules", "tools",
        "--collect-data", "tools",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
    ]
    pyinstaller.run(args)
    copy_vendor_data()

    exe = OUT / "adplus-backend" / ("adplus-backend.exe" if sys.platform == "win32" else "adplus-backend")
    if not exe.is_file():
        print(f"build finished but executable not found: {exe}", file=sys.stderr)
        return 1
    print(f"built: {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
