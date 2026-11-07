from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from adplus import project_store
from adplus.restyle import analysis, store


def make_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=#aa3333:s=320x640:r=30:d=1",
            "-f", "lavfi", "-i", "color=c=#33aa33:s=320x640:r=30:d=1",
            "-f", "lavfi", "-i", "color=c=#3333aa:s=320x640:r=30:d=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )


class RestyleStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-restyle-"))
        self.old_store_projects = store.PROJECTS
        self.old_store_workspace = store.WORKSPACE
        self.old_store_uploads = store.UPLOADS
        self.old_pstore_projects = project_store.PROJECTS
        self.old_analysis_projects = analysis.PROJECTS
        store.PROJECTS = self.tmp / "projects"
        store.WORKSPACE = self.tmp
        store.UPLOADS = self.tmp / "uploads"
        project_store.PROJECTS = self.tmp / "projects"
        analysis.PROJECTS = self.tmp / "projects"
        (self.tmp / "uploads").mkdir(parents=True)
        make_video(self.tmp / "uploads" / "demo.mp4")

    def tearDown(self) -> None:
        store.PROJECTS = self.old_store_projects
        store.WORKSPACE = self.old_store_workspace
        store.UPLOADS = self.old_store_uploads
        project_store.PROJECTS = self.old_pstore_projects
        analysis.PROJECTS = self.old_analysis_projects

    def test_create_detail_and_plan(self) -> None:
        record = store.create(str(self.tmp / "uploads" / "demo.mp4"), "demo", True)
        project_id = record["project"]["project_id"]
        self.assertTrue((self.tmp / "projects" / project_id / "restyle" / "source.json").is_file())
        self.assertFalse((self.tmp / "projects" / project_id / "restyle" / "blueprint.json").exists())

        detail = store.detail(project_id)
        assert detail is not None
        self.assertEqual(detail["plan"]["revision"], 1)
        plan = store.save_plan(project_id, {"change_level": "all"}, 1)
        self.assertEqual(plan["revision"], 2)
        self.assertEqual(len(store.list_restyles()), 1)

    def test_analysis_cuts_and_blueprint(self) -> None:
        record = store.create(str(self.tmp / "uploads" / "demo.mp4"), "demo", True)
        project_id = record["project"]["project_id"]
        blueprint = analysis.analyze_project(project_id)
        self.assertGreaterEqual(len(blueprint["shots"]), 2)
        self.assertLessEqual(len(blueprint["shots"]), 4)
        self.assertEqual(blueprint["shots"][0]["start_s"], 0.0)
        self.assertAlmostEqual(blueprint["shots"][-1]["end_s"], 3.0, delta=0.2)
        self.assertTrue((self.tmp / "projects" / project_id / "restyle" / "blueprint.json").is_file())


if __name__ == "__main__":
    unittest.main()
