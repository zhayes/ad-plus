from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from adplus import jobs, project_store
from adplus.restyle import analysis, store
from app.settings_server import app


def make_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=#884444:s=320x640:r=30:d=1",
            "-f", "lavfi", "-i", "color=c=#448844:s=320x640:r=30:d=1",
            "-f", "lavfi", "-i", "color=c=#444488:s=320x640:r=30:d=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )


class RestyleApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-restyle-api-"))
        self.old = (store.PROJECTS, store.WORKSPACE, store.UPLOADS, project_store.PROJECTS, analysis.PROJECTS)
        store.PROJECTS = self.tmp / "projects"
        store.WORKSPACE = self.tmp
        store.UPLOADS = self.tmp / "uploads"
        project_store.PROJECTS = self.tmp / "projects"
        analysis.PROJECTS = self.tmp / "projects"
        (self.tmp / "uploads").mkdir(parents=True)
        make_video(self.tmp / "uploads" / "demo.mp4")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        store.PROJECTS, store.WORKSPACE, store.UPLOADS, project_store.PROJECTS, analysis.PROJECTS = self.old
        self.client.close()

    def test_create_list_detail_and_plan(self) -> None:
        with mock.patch.object(jobs, "list_jobs", return_value=[]):
            created = self.client.post(
                "/api/restyle",
                json={"path": str(self.tmp / "uploads" / "demo.mp4"), "title": "demo", "rights_confirmed": True},
            )
            self.assertEqual(created.status_code, 200, created.text)
            project_id = created.json()["restyle"]["project"]["project_id"]
            listed = self.client.get("/api/restyle")
            self.assertEqual(len(listed.json()["restyles"]), 1)
            detail = self.client.get(f"/api/restyle/{project_id}")
            self.assertEqual(detail.status_code, 200)
            revision = detail.json()["plan"]["revision"]
            patched = self.client.patch(
                f"/api/restyle/{project_id}/plan",
                json={"revision": revision, "patch": {"change_level": "all"}},
            )
            self.assertEqual(patched.status_code, 200, patched.text)
            conflict = self.client.patch(
                f"/api/restyle/{project_id}/plan",
                json={"revision": 0, "patch": {"change_level": "light"}},
            )
            self.assertEqual(conflict.status_code, 409)


if __name__ == "__main__":
    unittest.main()
