"""Test package: isolate every test from the user's real projects.

``adplus.paths`` reads these env vars at import time, so they must be set
before any ``adplus`` / ``app`` module is imported.
"""

import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="adplus-tests-"))
(ROOT / "projects").mkdir(parents=True, exist_ok=True)
(ROOT / "brands").mkdir(parents=True, exist_ok=True)

os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(ROOT / "projects")
os.environ["ADPLUS_BRANDS_DIR"] = str(ROOT / "brands")
os.environ["OPENMONTAGE_UPLOADS_DIR"] = str(ROOT / "uploads")
os.environ["OPENMONTAGE_MUSIC_DIR"] = str(ROOT / "music")
