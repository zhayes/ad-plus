"""Windows/Linux CI smoke test for the Restyle P1 skeleton.

Creates a 3-second synthetic video with ffmpeg, then runs:
create project -> analyze -> plan patch.

Run from the repo root:
    python scripts/restyle_smoke.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adplus import project_store  # noqa: E402
from adplus.restyle import analysis, store  # noqa: E402


def make_video(path: Path) -> None:
    ffmpeg = analysis.FFMPEG
    colors = ["#aa3333", "#33aa33", "#3333aa"]
    inputs = []
    for color in colors:
        inputs += ["-f", "lavfi", "-i", f"color=c={color}:s=320x640:r=30:d=1"]
    subprocess.run(
        [
            ffmpeg, "-v", "error", "-y", *inputs,
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="adplus-restyle-smoke-"))
    old = (store.PROJECTS, store.WORKSPACE, store.UPLOADS, project_store.PROJECTS, analysis.PROJECTS)
    store.PROJECTS = tmp / "projects"
    store.WORKSPACE = tmp
    store.UPLOADS = tmp / "uploads"
    project_store.PROJECTS = tmp / "projects"
    analysis.PROJECTS = tmp / "projects"
    try:
        (tmp / "uploads").mkdir(parents=True)
        video = tmp / "uploads" / "smoke.mp4"
        make_video(video)
        record = store.create(str(video), "smoke", True)
        project_id = record["project"]["project_id"]
        blueprint = analysis.analyze_project(project_id)
        shots = blueprint.get("shots") or []
        assert 2 <= len(shots) <= 4, f"expected 2-4 shots, got {len(shots)}"
        assert blueprint["groups"]["scenes"], "no scene groups"
        detail = store.detail(project_id)
        revision = int((detail or {}).get("plan", {}).get("revision") or 1)
        plan = store.save_plan(project_id, {"change_level": "all"}, revision)
        assert plan["revision"] == revision + 1
        print(f"OK: {len(shots)} shots, {len(blueprint['groups']['scenes'])} scenes, {len(blueprint['groups']['outfits'])} outfits")
        return 0
    finally:
        store.PROJECTS, store.WORKSPACE, store.UPLOADS, project_store.PROJECTS, analysis.PROJECTS = old


if __name__ == "__main__":
    raise SystemExit(main())
