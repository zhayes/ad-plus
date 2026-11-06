from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adplus import canonical_artifacts, pipeline_runner, production
from adplus import project_store as ps


class PipelineRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-pipeline-"))
        self.old_projects = ps.PROJECTS
        self.old_canonical = canonical_artifacts.PROJECTS
        self.old_prod = production.PROJECTS
        self.old_runner = pipeline_runner.PROJECTS
        ps.PROJECTS = self.tmp / "projects"
        canonical_artifacts.PROJECTS = ps.PROJECTS
        production.PROJECTS = ps.PROJECTS
        pipeline_runner.PROJECTS = ps.PROJECTS
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        ps.create_project(
            "avatar test", project_id="avatar-test", platform="douyin", duration_s=10,
            brief={"product": "YACHEL", "selling_points": ["冰丝"]},
            route={"id": "avatar_spokesperson"},
        )
        ps.create_version("avatar-test", "v1", copy_shots=False)
        ps.add_shot("avatar-test", "v1", description="主播", duration_s=10)
        (ps.PROJECTS / "avatar-test" / "artifacts" / "script.json").write_text(
            json.dumps({"lines": [{"id": "l1", "text": "夏天穿背心。"}]}, ensure_ascii=False),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        ps.PROJECTS = self.old_projects
        canonical_artifacts.PROJECTS = self.old_canonical
        production.PROJECTS = self.old_prod
        pipeline_runner.PROJECTS = self.old_runner

    def test_sync_bootstrap_writes_checkpoints(self) -> None:
        result = pipeline_runner.sync_and_bootstrap("avatar-test", "v1", approve=True)
        self.assertEqual(set(result["checkpoints"]), {"idea", "script", "scene_plan"})
        for stage in ("idea", "script", "scene_plan"):
            cp = pipeline_runner._checkpoint().read_checkpoint(ps.PROJECTS, "avatar-test", stage)
            self.assertIsNotNone(cp)
            assert cp is not None
            self.assertEqual(cp["pipeline_type"], "avatar-spokesperson")
            self.assertEqual(cp["status"], "completed")
            self.assertTrue(cp["human_approved"])
        self.assertEqual(pipeline_runner.next_stage("avatar-test"), "assets")

    def test_production_board_uses_checkpoint_status(self) -> None:
        pipeline_runner.sync_and_bootstrap("avatar-test", "v1", approve=True)
        payload = production.production_payload("avatar-test")
        self.assertIsNotNone(payload)
        assert payload is not None
        brief = next(row for row in payload["stages"] if row["id"] == "brief")
        self.assertEqual(brief["canonical_stage"], "idea")
        self.assertEqual(brief["checkpoint_status"], "completed")
        self.assertEqual(brief["status"], "approved")
        self.assertEqual(payload["checkpoints"]["idea"], "completed")

    def test_partial_checkpoint_overrides_legacy_stage_state(self) -> None:
        pipeline_runner.init_project("avatar-test")
        brief = canonical_artifacts.read("avatar-test", "brief") if canonical_artifacts.read("avatar-test", "brief") else None
        # write brief through canonical sync first, but only the idea checkpoint
        canonical_artifacts.sync_project("avatar-test", "v1")
        brief = canonical_artifacts.read("avatar-test", "brief")
        assert brief is not None
        pipeline_runner.write_stage("avatar-test", "idea", {"brief": brief}, approved=True)
        payload = production.production_payload("avatar-test")
        assert payload is not None
        rows = {row["id"]: row for row in payload["stages"]}
        self.assertTrue(payload["pipeline_mode"])
        self.assertEqual(rows["brief"]["status"], "approved")
        self.assertEqual(rows["script"]["status"], "ready")
        self.assertEqual(rows["scene"]["status"], "locked")

    def test_asset_stage_can_be_written_with_manifest(self) -> None:
        pipeline_runner.sync_and_bootstrap("avatar-test", "v1", approve=True)
        manifest = canonical_artifacts.read("avatar-test", "asset_manifest")
        assert manifest is not None
        cp = pipeline_runner.write_stage(
            "avatar-test", "assets", {"asset_manifest": manifest}, approved=True,
        )
        self.assertEqual(cp["stage"], "assets")
        self.assertEqual(cp["status"], "completed")
        self.assertEqual(pipeline_runner.next_stage("avatar-test"), "edit")


class AssetsStageBlockedTest(unittest.TestCase):
    def setUp(self) -> None:
        import os
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-assets-"))
        self.old_projects = ps.PROJECTS
        self.old_canonical = canonical_artifacts.PROJECTS
        self.old_prod = production.PROJECTS
        self.old_runner = pipeline_runner.PROJECTS
        self.old_dh = pipeline_runner.digital_human.PROJECTS
        self.old_personas = pipeline_runner.digital_human.personas.PERSONAS
        self.old_products = pipeline_runner.digital_human.products.PRODUCTS
        self.old_state = pipeline_runner.digital_human.capabilities.STATE_DIR
        self.old_key = os.environ.pop("KLING_API_KEY", None)
        ps.PROJECTS = self.tmp / "projects"
        canonical_artifacts.PROJECTS = ps.PROJECTS
        production.PROJECTS = ps.PROJECTS
        pipeline_runner.PROJECTS = ps.PROJECTS
        pipeline_runner.digital_human.PROJECTS = ps.PROJECTS
        pipeline_runner.digital_human.personas.PERSONAS = self.tmp / "personas"
        pipeline_runner.digital_human.products.PRODUCTS = self.tmp / "products"
        pipeline_runner.digital_human.capabilities.STATE_DIR = self.tmp / "state"
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads").mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads" / "model.png").write_bytes(b"png")
        (self.tmp / "uploads" / "voice.wav").write_bytes(b"wav")
        ps.create_project("blocked", project_id="asset-test", platform="douyin", duration_s=10)
        ps.create_version("asset-test", "v1", copy_shots=False)
        ps.add_shot(
            "asset-test", "v1", description="主播", duration_s=10,
            production_method="avatar", persona_id="p_test",
            generation_spec={"profile": "kling-avatar", "audio_path": "uploads/voice.wav"},
        )
        (ps.PROJECTS / "asset-test" / "artifacts" / "script.json").write_text(
            json.dumps({"lines": [{"id": "l1", "text": "测试"}]}, ensure_ascii=False), encoding="utf-8",
        )
        pipeline_runner.digital_human.personas.save_persona({
            "id": "p_test", "name": "小夏", "kind": "photo", "source_path": "uploads/model.png",
            "rights": {"ai_allowed": True, "consent": True},
        })

    def tearDown(self) -> None:
        import os
        ps.PROJECTS = self.old_projects
        canonical_artifacts.PROJECTS = self.old_canonical
        production.PROJECTS = self.old_prod
        pipeline_runner.PROJECTS = self.old_runner
        pipeline_runner.digital_human.PROJECTS = self.old_dh
        pipeline_runner.digital_human.personas.PERSONAS = self.old_personas
        pipeline_runner.digital_human.products.PRODUCTS = self.old_products
        pipeline_runner.digital_human.capabilities.STATE_DIR = self.old_state
        if self.old_key is not None:
            os.environ["KLING_API_KEY"] = self.old_key
        pipeline_runner.digital_human.capabilities.clear_health()

    def test_blocked_take_writes_failed_checkpoint(self) -> None:
        result = pipeline_runner.run_assets_stage(
            "asset-test", shot_id="s1", profile_id="kling-avatar",
            persona_id="p_test", audio_path="uploads/voice.wav", execute=True,
        )
        self.assertEqual(result["status"], "blocked")
        cp = result["checkpoint"]
        self.assertEqual(cp["stage"], "assets")
        self.assertEqual(cp["status"], "failed")
        self.assertTrue(cp["error"])


class AssetsStageSuccessTest(unittest.TestCase):
    def test_fake_tool_reaches_completed_assets_checkpoint(self) -> None:
        import os
        import tempfile
        from pathlib import Path
        from tools.base_tool import BaseTool, ToolResult
        from tools.tool_registry import registry

        class FakeLip(BaseTool):
            name = "fake_lip_for_test"
            capability = "lip_sync"
            provider = "local"

            def execute(self, inputs):
                out = Path(inputs["output_path"])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"fake")
                return ToolResult(success=True, data={"output": str(out)})

        tmp = Path(tempfile.mkdtemp(prefix="adplus-assets-ok-"))
        old_projects = ps.PROJECTS
        old_canonical = canonical_artifacts.PROJECTS
        old_prod = production.PROJECTS
        old_runner = pipeline_runner.PROJECTS
        old_dh = pipeline_runner.digital_human.PROJECTS
        old_personas = pipeline_runner.digital_human.personas.PERSONAS
        old_map = dict(pipeline_runner.digital_human.ADAPTER_TOOLS)
        old_path = os.environ.get("WAV2LIP_PATH")
        ps.PROJECTS = tmp / "projects"
        canonical_artifacts.PROJECTS = ps.PROJECTS
        production.PROJECTS = ps.PROJECTS
        pipeline_runner.PROJECTS = ps.PROJECTS
        pipeline_runner.digital_human.PROJECTS = ps.PROJECTS
        pipeline_runner.digital_human.personas.PERSONAS = tmp / "personas"
        pipeline_runner.digital_human.products.PRODUCTS = tmp / "products"
        pipeline_runner.digital_human.capabilities.STATE_DIR = tmp / "state"
        pipeline_runner.digital_human.ADAPTER_TOOLS["wav2lip"] = "fake_lip_for_test"
        os.environ["WAV2LIP_PATH"] = str(tmp / "wav2lip")
        registry.register(FakeLip())
        (tmp / "uploads").mkdir(parents=True, exist_ok=True)
        (tmp / "uploads" / "model.png").write_bytes(b"png")
        (tmp / "uploads" / "voice.wav").write_bytes(b"wav")
        (tmp / "uploads" / "base.mp4").write_bytes(b"mp4")
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        ps.create_project("ok", project_id="ok-test", platform="douyin", duration_s=5)
        ps.create_version("ok-test", "v1", copy_shots=False)
        ps.add_shot(
            "ok-test", "v1", description="主播", duration_s=5,
            production_method="lip_sync", persona_id="p_ok",
            asset_refs={"source_video": "uploads/base.mp4"},
            generation_spec={"profile": "wav2lip", "audio_path": "uploads/voice.wav"},
        )
        (ps.PROJECTS / "ok-test" / "artifacts" / "script.json").write_text(
            json.dumps({"lines": [{"id": "l1", "text": "测试"}]}, ensure_ascii=False), encoding="utf-8",
        )
        pipeline_runner.digital_human.personas.save_persona({
            "id": "p_ok", "name": "小夏", "kind": "photo", "source_path": "uploads/model.png",
            "rights": {"ai_allowed": True, "consent": True},
        })
        try:
            result = pipeline_runner.run_assets_stage(
                "ok-test", shot_id="s1", profile_id="wav2lip", persona_id="p_ok", execute=True,
            )
            self.assertEqual(result["status"], "done", result)
            self.assertEqual(result["checkpoint"]["status"], "completed")
            self.assertTrue(result["checkpoint"]["human_approved"])
            self.assertEqual(result["checkpoint"]["artifacts"]["asset_manifest"]["assets"][0]["type"], "video")
        finally:
            ps.PROJECTS = old_projects
            canonical_artifacts.PROJECTS = old_canonical
            production.PROJECTS = old_prod
            pipeline_runner.PROJECTS = old_runner
            pipeline_runner.digital_human.PROJECTS = old_dh
            pipeline_runner.digital_human.personas.PERSONAS = old_personas
            pipeline_runner.digital_human.ADAPTER_TOOLS.clear()
            pipeline_runner.digital_human.ADAPTER_TOOLS.update(old_map)
            if old_path is None:
                os.environ.pop("WAV2LIP_PATH", None)
            else:
                os.environ["WAV2LIP_PATH"] = old_path
