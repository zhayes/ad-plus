from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import product_composite, products
from adplus import project_store as ps


class ProductCompositePlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-plate-"))
        self.old_projects = ps.PROJECTS
        self.old_plate_projects = product_composite.PROJECTS
        self.old_products = products.PRODUCTS
        ps.PROJECTS = self.tmp / "projects"
        product_composite.PROJECTS = ps.PROJECTS
        products.PRODUCTS = self.tmp / "products"
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads").mkdir(parents=True, exist_ok=True)
        (self.tmp / "uploads" / "hero.jpg").write_bytes(b"jpg")
        (self.tmp / "uploads" / "base.mp4").write_bytes(b"mp4")
        ps.create_project("贴片测试", project_id="plate-test")
        ps.create_version("plate-test", "v1", copy_shots=False)
        ps.add_shot(
            "plate-test", "v1", description="主播", duration_s=10,
            production_method="image_to_video", product_id="prod_plate",
            generation_spec={"base_video_path": "uploads/base.mp4"},
        )
        products.save_product({
            "id": "prod_plate", "name": "背心", "hero_path": "uploads/hero.jpg",
            "locked": True, "label_text": "YACHEL",
            "rights": {"ai_reference_allowed": True, "commercial_use": True},
        })

    def tearDown(self) -> None:
        ps.PROJECTS = self.old_projects
        product_composite.PROJECTS = self.old_plate_projects
        products.PRODUCTS = self.old_products

    def test_ready_plan(self) -> None:
        take = product_composite.plan("plate-test", shot_id="s1", version_id="v1", product_id="prod_plate")
        self.assertEqual(take["status"], "ready", take["blockers"])
        self.assertEqual(take["product_id"], "prod_plate")
        self.assertEqual(take["input"]["product_image"], "uploads/hero.jpg")
        self.assertTrue(take["output_path"].startswith("projects/plate-test/renders/"))

    def test_unlocked_product_blocks(self) -> None:
        products.save_product({
            "name": "未锁定", "hero_path": "uploads/hero.jpg", "locked": False,
            "rights": {"ai_reference_allowed": True},
        }, "prod_plate")
        take = product_composite.plan("plate-test", shot_id="s1", version_id="v1", product_id="prod_plate")
        self.assertEqual(take["status"], "blocked")
        self.assertTrue(any("未锁定" in item for item in take["blockers"]))
