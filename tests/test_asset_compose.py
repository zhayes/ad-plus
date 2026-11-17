from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from adplus import asset_compose, project_store


class AssetComposeTest(unittest.TestCase):
    def test_bound_shots_are_concatenated(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not installed")
        root = Path(tempfile.mkdtemp(prefix="adplus-compose-"))
        old_projects = project_store.PROJECTS
        old_update, old_finish = asset_compose.job_store.update, asset_compose.job_store.finish
        project_store.PROJECTS = root / "projects"
        asset_compose.project_store.PROJECTS = project_store.PROJECTS
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("compose", project_id="compose-test", aspect="9:16", duration_s=4)
        project_store.create_version("compose-test", "v1", copy_shots=False)
        clips = []
        for index in range(2):
            clip = root / f"shot{index}.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s=1080x1920:d=2",
                 "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)],
                check=True, timeout=30,
            )
            clips.append(str(clip))
        version = project_store.add_shot("compose-test", "v1", description="a", duration_s=2)
        project_store.update_shot("compose-test", "v1", version["shots"][0]["id"], {"preview": clips[0]})
        version = project_store.add_shot("compose-test", "v1", description="b", duration_s=2)
        project_store.update_shot("compose-test", "v1", version["shots"][1]["id"], {"preview": clips[1]})
        asset_compose.job_store.update = lambda job, **fields: job
        asset_compose.job_store.finish = lambda job, status, **fields: job
        version = project_store.load_version("compose-test", "v1")
        job = {"id": "j1", "project_id": "compose-test", "log_tail": []}
        try:
            asset_compose._run("compose-test", job, [Path(path) for path in clips], root / "out.mp4")
            version = project_store.load_version("compose-test", "v1")
            self.assertIsNotNone(version.get("render"))
            self.assertTrue(Path(root / "out.mp4").is_file())
        finally:
            project_store.PROJECTS = old_projects
            asset_compose.project_store.PROJECTS = old_projects
            asset_compose.job_store.update, asset_compose.job_store.finish = old_update, old_finish
