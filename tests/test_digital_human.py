from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from adplus import capabilities, digital_human, personas, products
from adplus import project_store as ps


class DigitalHumanPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-dh-"))
        self.old = {
            "projects": ps.PROJECTS,
            "dh_projects": digital_human.PROJECTS,
            "personas": personas.PERSONAS,
            "products": products.PRODUCTS,
            "state": capabilities.STATE_DIR,
            "key": os.environ.get("KLING_API_KEY"),
        }
        ps.PROJECTS = self.tmp / "projects"
        digital_human.PROJECTS = ps.PROJECTS
        personas.PERSONAS = self.tmp / "personas"
        products.PRODUCTS = self.tmp / "products"
        capabilities.STATE_DIR = self.tmp / "state"
        os.environ["KLING_API_KEY"] = "test-key"
        capabilities.clear_health()
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads").mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads" / "model.jpg").write_bytes(b"jpg")
        (self.tmp / "uploads" / "product.jpg").write_bytes(b"jpg")
        (self.tmp / "uploads" / "voice.wav").write_bytes(b"wav")
        ps.create_project("数字人测试", project_id="dh-test")
        ps.create_version("dh-test", "v1", copy_shots=False)
        ps.add_shot(
            "dh-test", "v1", description="主播讲解", duration_s=10,
            production_method="avatar", persona_id="p_test", product_id="prod_test",
            generation_spec={"profile": "kling-avatar", "audio_path": "uploads/voice.wav"},
        )
        personas.save_persona({
            "id": "p_test", "name": "小夏", "kind": "photo",
            "source_path": "uploads/model.jpg",
            "rights": {"ai_allowed": True, "consent": True},
        })
        products.save_product({
            "id": "prod_test", "name": "背心", "hero_path": "uploads/product.jpg",
            "locked": True, "rights": {"ai_reference_allowed": True, "commercial_use": True},
        })

    def tearDown(self) -> None:
        ps.PROJECTS = self.old["projects"]
        digital_human.PROJECTS = self.old["dh_projects"]
        personas.PERSONAS = self.old["personas"]
        products.PRODUCTS = self.old["products"]
        capabilities.STATE_DIR = self.old["state"]
        if self.old["key"] is None:
            os.environ.pop("KLING_API_KEY", None)
        else:
            os.environ["KLING_API_KEY"] = self.old["key"]
        capabilities.clear_health()

    def test_ready_plan_binds_persona_and_product(self) -> None:
        take = digital_human.plan(
            "dh-test", shot_id="s1", profile_id="kling-avatar",
            persona_id="p_test", product_id="prod_test",
        )
        self.assertEqual(take["status"], "ready", take["blockers"])
        self.assertEqual(take["persona_id"], "p_test")
        self.assertEqual(take["product_id"], "prod_test")
        self.assertEqual(take["input"]["persona_image"], "uploads/model.jpg")
        self.assertEqual(take["input"]["product_image"], "uploads/product.jpg")
        self.assertTrue(take["output_path"].startswith("projects/dh-test/renders/"))

    def test_missing_consent_no_longer_blocks_take(self) -> None:
        personas.save_persona({"name": "小夏", "kind": "photo", "source_path": "uploads/model.jpg", "rights": {"ai_allowed": True, "consent": False}}, "p_test")
        take = digital_human.plan(
            "dh-test", shot_id="s1", profile_id="kling-avatar",
            persona_id="p_test", product_id="prod_test",
        )
        self.assertEqual(take["status"], "ready", take["blockers"])
        self.assertFalse(any("授权" in item for item in take["blockers"]))

    def test_wav2lip_requires_source_video(self) -> None:
        take = digital_human.plan(
            "dh-test", shot_id="s1", profile_id="wav2lip",
            persona_id="p_test", product_id="prod_test",
        )
        self.assertEqual(take["status"], "blocked")
        self.assertTrue(any("基础表演视频" in item for item in take["blockers"]))
