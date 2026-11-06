from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from adplus import capabilities, personas, project_store as ps


class PersonaStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-personas-"))
        self.old = personas.PERSONAS
        personas.PERSONAS = self.tmp / "personas"

    def tearDown(self) -> None:
        personas.PERSONAS = self.old

    def test_crud_and_rights_defaults(self) -> None:
        first = personas.save_persona(
            {"name": "小夏", "kind": "photo", "source_path": "uploads/1/xia.jpg", "tags": ["clean"]}
        )
        self.assertEqual(first["kind"], "photo")
        self.assertFalse(first["rights"]["ai_allowed"])
        self.assertFalse(first["rights"]["consent"])
        self.assertEqual(first["tags"], ["clean"])
        rows = personas.list_personas()
        self.assertEqual([row["id"] for row in rows], [first["id"]])
        updated = personas.save_persona(
            {"rights": {"ai_allowed": True, "consent": True, "commercial_use": True}},
            first["id"],
        )
        self.assertTrue(updated["rights"]["ai_allowed"])
        self.assertEqual(updated["name"], "小夏")
        self.assertTrue(personas.delete_persona(first["id"]))
        self.assertEqual(personas.list_personas(), [])

    def test_photo_requires_image(self) -> None:
        with self.assertRaises(ValueError):
            personas.save_persona({"name": "无图", "kind": "photo"})


class ModelPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-health-"))
        self.old_state = capabilities.STATE_DIR
        self.old_key = os.environ.get("ARK_API_KEY")
        capabilities.STATE_DIR = self.tmp
        os.environ["ARK_API_KEY"] = "test-key"
        capabilities.clear_health()

    def tearDown(self) -> None:
        capabilities.STATE_DIR = self.old_state
        if self.old_key is None:
            os.environ.pop("ARK_API_KEY", None)
        else:
            os.environ["ARK_API_KEY"] = self.old_key
        capabilities.clear_health()

    def test_seedance_480p_5s_is_ready(self) -> None:
        result = capabilities.preflight(
            "seedance-2.0", resolution="480p", duration=5, operation="image_to_video"
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["profile"]["model"], "doubao-seedance-2-0-260128")

    def test_seedance_rejects_wrong_duration(self) -> None:
        result = capabilities.preflight("seedance-2.0", resolution="480p", duration=20)
        self.assertFalse(result["ok"])
        self.assertTrue(any("duration" in item for item in result["blockers"]))

    def test_provider_health_blocks_without_changing_profile(self) -> None:
        capabilities.record_health("seedance-2.0", "blocked", "ModelNotOpen", "模型服务未开通", ttl_seconds=60)
        result = capabilities.preflight("seedance-2.0", resolution="480p", duration=5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "blocked")
        self.assertIn("模型服务未开通", result["blockers"])
        capabilities.clear_health("seedance-2.0")
        self.assertTrue(capabilities.preflight("seedance-2.0", resolution="480p", duration=5)["ok"])

    def test_seedance_2_5_warns_custom_price(self) -> None:
        result = capabilities.preflight("seedance-2.5", resolution="480p", duration=10, operation="reference_to_video")
        self.assertTrue(result["ok"], result)
        self.assertTrue(any("price" in item.lower() for item in result["warnings"]))


class ShotContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-shots-"))
        self.old_projects = ps.PROJECTS
        ps.PROJECTS = self.tmp / "projects"
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        ps.PROJECTS = self.old_projects

    def test_shot_generation_fields_survive(self) -> None:
        ps.create_project("测试", project_id="shot-contract")
        ps.create_version("shot-contract", "v1", copy_shots=False)
        version = ps.add_shot(
            "shot-contract", "v1", description="主播拿衣服", duration_s=10,
            production_method="reference_to_video",
            persona_id="p_demo", product_id="prod_demo",
            asset_refs={"presenter": "p_demo", "product": "asset_product"},
            generation_spec={"profile": "seedance-2.5", "resolution": "480p", "duration": 10},
            shot_language={"shot_size": "medium", "camera_movement": "handheld"},
            timeline={"slot_duration_s": 10, "actual_duration_s": 10.04},
        )
        shot = version["shots"][0]
        self.assertEqual(shot["production_method"], "reference_to_video")
        self.assertEqual(shot["persona_id"], "p_demo")
        self.assertEqual(shot["asset_refs"]["presenter"], "p_demo")
        self.assertEqual(shot["generation_spec"]["profile"], "seedance-2.5")
        self.assertEqual(shot["timeline"]["actual_duration_s"], 10.04)
        self.assertEqual((shot["start_s"], shot["end_s"]), (0.0, 10.0))


class PipelineAdapterTest(unittest.TestCase):
    def test_avatar_pipeline_facts_come_from_manifest(self) -> None:
        from adplus import pipeline_adapter

        view = pipeline_adapter.route_view("avatar_spokesperson")
        self.assertTrue(view["available"], view)
        self.assertEqual(view["pipeline"], "avatar-spokesperson")
        self.assertEqual(view["stages"], ["idea", "script", "scene_plan", "assets", "edit", "compose", "publish"])
        self.assertEqual(view["stage_artifacts"]["assets"], "asset_manifest")
        self.assertEqual(view["stage_artifacts"]["compose"], "render_report")

    def test_route_to_pipeline_is_not_a_second_pipeline(self) -> None:
        from adplus import pipeline_adapter

        self.assertEqual(pipeline_adapter.pipeline_for_route("avatar_spokesperson"), "avatar-spokesperson")
        self.assertEqual(pipeline_adapter.pipeline_for_route("local_motion"), "animation")
        self.assertEqual(pipeline_adapter.STAGE_MAP["review"], "publish")


class ProductionPipelineProjectionTest(unittest.TestCase):
    def test_payload_exposes_canonical_stages(self) -> None:
        import tempfile
        from pathlib import Path
        from adplus import production
        from adplus import project_store as ps

        tmp = Path(tempfile.mkdtemp(prefix="adplus-prod-"))
        old_ps, old_prod = ps.PROJECTS, production.PROJECTS
        ps.PROJECTS = tmp / "projects"
        production.PROJECTS = ps.PROJECTS
        try:
            ps.create_project("投影测试", project_id="proj-test", route={"id": "avatar_spokesperson"})
            payload = production.production_payload("proj-test")
            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload["pipeline"]["pipeline"], "avatar-spokesperson")
            self.assertEqual(payload["pipeline"]["stages"][0], "idea")
            self.assertEqual(payload["stage_projection"]["review"], "publish")
            canonical = next(row for row in payload["routes"] if row["id"] == "avatar_spokesperson")["canonical"]
            self.assertEqual(canonical["stage_artifacts"]["assets"], "asset_manifest")
        finally:
            ps.PROJECTS, production.PROJECTS = old_ps, old_prod
