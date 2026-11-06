from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adplus import canonical_artifacts, production
from adplus import project_store as ps


class CanonicalArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-canonical-"))
        self.old_projects = ps.PROJECTS
        self.old_canonical = canonical_artifacts.PROJECTS
        self.old_prod = production.PROJECTS
        ps.PROJECTS = self.tmp / "projects"
        canonical_artifacts.PROJECTS = ps.PROJECTS
        production.PROJECTS = ps.PROJECTS
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        ps.create_project(
            "YACHEL 10s", project_id="canon-test", platform="douyin", duration_s=10,
            brief={"product": "YACHEL 背心", "selling_points": ["冰丝", "无痕"], "cta": "点击购买"},
        )
        ps.create_version("canon-test", "v1", copy_shots=False)
        ps.add_shot(
            "canon-test", "v1", description="主播讲解", duration_s=10,
            preview="projects/canon-test/assets/frame.jpg", production_method="image_to_video",
        )
        script = {"lines": [{"id": "l1", "text": "夏天穿背心，最怕闷汗。"}]}
        (ps.PROJECTS / "canon-test" / "artifacts" / "script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        ps.PROJECTS = self.old_projects
        canonical_artifacts.PROJECTS = self.old_canonical
        production.PROJECTS = self.old_prod

    def test_sync_writes_schema_valid_artifacts(self) -> None:
        from schemas.artifacts import validate_artifact

        result = canonical_artifacts.sync_project("canon-test", "v1")
        self.assertEqual(set(result["artifacts"]), {"brief", "script", "scene_plan", "asset_manifest"})
        for name, path in result["artifacts"].items():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            validate_artifact(name, data)
        brief = canonical_artifacts.read("canon-test", "brief")
        assert brief is not None
        self.assertEqual(brief["target_platform"], "tiktok")
        scene = canonical_artifacts.read("canon-test", "scene_plan")
        assert scene is not None
        self.assertEqual(scene["scenes"][0]["type"], "generated")
