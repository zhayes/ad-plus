from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import production, project_store


class ProductionGateTest(unittest.TestCase):
    def test_settings_revision_invalidates_assets_and_render(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-gates-"))
        old = project_store.PROJECTS
        project_store.PROJECTS = root / "projects"
        production.PROJECTS = project_store.PROJECTS
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("gate", project_id="gate-test", route={"id": "avatar_spokesperson"}, duration_s=4)
        project_store.create_version("gate-test", "v1", copy_shots=False)
        version = project_store.add_shot("gate-test", "v1", description="a", duration_s=2, persona_id="p")
        project_store.update_shot("gate-test", "v1", version["shots"][0]["id"], {"preview": "projects/gate-test/renders/a.mp4"})
        version = project_store.load_version("gate-test", "v1")
        version["settings_revision"] = 1
        version["render"] = {"path": "projects/gate-test/renders/final.mp4", "settings_revision": 1}
        project_store.save_version(version)
        project_store.update_project("gate-test", {
            "production_settings": {"revision": 1, "output": {"aspect": "9:16", "duration_s": 4, "resolution": "480p", "fps": 30, "platform": "douyin"}, "generation": {"audio_mode": "external_tts", "mode": "auto", "quality_tier": "draft", "budget_usd": 2.0}},
        })
        project = project_store.load_project("gate-test")
        settings = project["production_settings"]
        settings["revision"] = 2
        settings["output"]["resolution"] = "720p"
        project_store.update_project("gate-test", {"production_settings": settings})
        try:
            payload = production.production_payload("gate-test")
            stages = {row["id"]: row for row in payload["stages"]}
            self.assertNotEqual(stages["assets"]["status"], "approved")
            self.assertNotEqual(stages["compose"]["status"], "approved")
            self.assertNotEqual(stages["review"]["status"], "approved")
        finally:
            project_store.PROJECTS = old
            production.PROJECTS = old
