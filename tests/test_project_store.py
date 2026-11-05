from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adplus import assets as asset_store
from adplus import project_store as ps


def scene(index: int, start: float, end: float, role: str = "build") -> dict:
    return {
        "id": f"s{index}",
        "start_seconds": start,
        "end_seconds": end,
        "description": f"镜头 {index}",
        "narrative_role": role,
    }


class ProjectStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-store-"))
        self.old_projects, self.old_brands = ps.PROJECTS, ps.BRANDS
        self.old_uploads = asset_store.UPLOADS
        ps.PROJECTS = self.tmp / "projects"
        ps.BRANDS = self.tmp / "brands"
        asset_store.PROJECTS = ps.PROJECTS
        asset_store.UPLOADS = self.tmp / "uploads"
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        asset_store.UPLOADS.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        ps.PROJECTS, ps.BRANDS = self.old_projects, self.old_brands
        asset_store.PROJECTS = self.old_projects
        asset_store.UPLOADS = self.old_uploads

    def _project(self, pid: str = "sweet-potato-15s", scenes: list | None = None) -> dict:
        project = ps.create_project("红薯 · 炭火现烤 15s", project_id=pid, platform="douyin", duration_s=15)
        if scenes is not None:
            path = self.tmp / "projects" / pid / "artifacts" / "scene_plan.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8")
        return project

    def test_create_list_and_normalise(self) -> None:
        project = self._project()
        self.assertEqual(project["version"], "2.0")
        rows = ps.list_projects()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "sweet-potato-15s")
        self.assertEqual(rows[0]["pending_count"], 0)
        self.assertEqual(rows[0]["version_count"], 0)

    def test_bootstrap_version_from_scene_plan(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        version = ps.ensure_version("sweet-potato-15s")
        self.assertIsNotNone(version)
        assert version is not None
        self.assertEqual([s["id"] for s in version["shots"]], ["s1", "s2", "s3"])
        self.assertEqual([(s["start_s"], s["end_s"]) for s in version["shots"]],
                         [(0.0, 2.0), (2.0, 5.0), (5.0, 7.5)])
        self.assertEqual(ps.load_project("sweet-potato-15s")["current_version_id"], "v1")

    def test_reorder_preserves_durations(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        version = ps.reorder_shots("sweet-potato-15s", "v1", ["s2", "s1", "s3"])
        self.assertEqual([s["id"] for s in version["shots"]], ["s2", "s1", "s3"])
        self.assertEqual([(s["start_s"], s["end_s"]) for s in version["shots"]],
                         [(0.0, 3.0), (3.0, 5.0), (5.0, 7.5)])
        self.assertEqual(version["duration_s"], 7.5)

    def test_add_update_delete_shot(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        version = ps.add_shot("sweet-potato-15s", "v1", after_id="s2", description="新镜头", duration_s=1.5)
        self.assertEqual([s["id"] for s in version["shots"]], ["s1", "s2", "s4", "s3"])
        self.assertEqual(version["duration_s"], 9.0)

        shot = ps.update_shot("sweet-potato-15s", "v1", "s4", {"duration_s": 3.0, "locked": True})
        self.assertEqual(shot["duration_s"], 3.0)
        self.assertTrue(shot["locked"])
        self.assertEqual(ps.load_version("sweet-potato-15s", "v1")["duration_s"], 10.5)

        version = ps.delete_shot("sweet-potato-15s", "v1", "s2")
        self.assertEqual([s["id"] for s in version["shots"]], ["s1", "s4", "s3"])
        self.assertEqual(version["duration_s"], 7.5)

    def test_delete_last_shot_leaves_empty_draft(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5)])
        ps.ensure_version("sweet-potato-15s")
        ps.delete_shot("sweet-potato-15s", "v1", "s1")
        version = ps.delete_shot("sweet-potato-15s", "v1", "s2")
        self.assertEqual(version["shots"], [])
        self.assertEqual(version["duration_s"], 0)
        added = ps.add_shot("sweet-potato-15s", "v1", description="重新开始", duration_s=2.0)
        self.assertEqual(len(added["shots"]), 1)
        self.assertEqual(added["duration_s"], 2.0)

    def test_brand_snapshot_is_immutable(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        brand = ps.save_brand({"name": "红薯铺", "colors": ["#E0338A"], "banned_words": ["最"]})
        ps.apply_brand("sweet-potato-15s", brand["id"])

        v2 = ps.create_version("sweet-potato-15s")
        self.assertEqual(v2["brand_snapshot"]["name"], "红薯铺")
        self.assertEqual(ps.load_project("sweet-potato-15s")["current_version_id"], v2["id"])

        ps.save_brand({"name": "红薯铺 2.0"}, brand["id"])
        old = ps.load_version("sweet-potato-15s", v2["id"])
        self.assertEqual(old["brand_snapshot"]["name"], "红薯铺")

        v3 = ps.create_version("sweet-potato-15s")
        self.assertEqual(v3["brand_snapshot"]["name"], "红薯铺 2.0")
        self.assertNotEqual(v2["id"], v3["id"])

    def test_pending_records_and_detail(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        quote_dir = self.tmp / "projects" / "sweet-potato-15s" / "quotes"
        quote_dir.mkdir(parents=True)
        (quote_dir / "q_test.json").write_text(json.dumps({"id": "q_test", "status": "pending", "total_usd": 0.2}), encoding="utf-8")
        detail = ps.project_detail("sweet-potato-15s")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(len(detail["pending"]), 1)
        self.assertEqual(detail["current_version"]["id"], "v1")
        self.assertEqual(detail["current_version"]["shots_count"], 3)
        self.assertEqual(ps.project_summary(ps.load_project("sweet-potato-15s"))["pending_count"], 1)

    def test_plan_payload_and_keyframes(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        quote_dir = self.tmp / "projects" / "sweet-potato-15s" / "quotes"
        quote_dir.mkdir(parents=True)
        (quote_dir / "q1.json").write_text(json.dumps({"id": "q1", "status": "pending", "total_usd": 0.2, "headline": "15s 方案"}), encoding="utf-8")
        proposal = self.tmp / "projects" / "sweet-potato-15s" / "artifacts" / "proposal_packet.json"
        proposal.write_text(json.dumps({"selected_concept": {"concept_id": "c1"}, "concept_options": [{"id": "c1", "title": "流糖"}]}, ensure_ascii=False), encoding="utf-8")
        frame_dir = self.tmp / "projects" / "sweet-potato-15s" / "review"
        frame_dir.mkdir(parents=True)
        for name in ("t0.png", "t2.png", "t4.png", "t6.png"):
            (frame_dir / name).write_bytes(b"png")
        payload = ps.plan_payload("sweet-potato-15s")
        assert payload is not None
        self.assertEqual(payload["quote"]["id"], "q1")
        self.assertEqual(len(payload["keyframes"]), 3)
        self.assertEqual(payload["proposal"]["selected_concept"]["concept_id"], "c1")

    def test_review_qa_and_export(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        brand = ps.save_brand({"name": "红薯铺", "banned_words": ["最"]})
        ps.apply_brand("sweet-potato-15s", brand["id"])
        # recreate the version after applying the brand so the snapshot carries it
        Version = ps.ensure_version("sweet-potato-15s")
        assert Version is not None
        render_file = self.tmp / "projects" / "sweet-potato-15s" / "renders" / "test.mp4"
        render_file.parent.mkdir(parents=True, exist_ok=True)
        render_file.write_bytes(b"fake-mp4")
        ps.update_version("sweet-potato-15s", "v1", {"render": {"path": "projects/sweet-potato-15s/renders/test.mp4", "width": 1080, "height": 1920}})
        final = self.tmp / "projects" / "sweet-potato-15s" / "artifacts" / "final_review.json"
        final.write_text(json.dumps({"status": "pass", "checks": {"technical_probe": {"verdict": "pass", "detail": "ok"}}, "issues_found": []}), encoding="utf-8")
        # brand word appears in a shot description -> QA fail
        ps.update_shot("sweet-potato-15s", "v1", "s1", {"description": "全网最好吃"})
        payload = ps.review_payload("sweet-potato-15s", "v1")
        assert payload is not None
        self.assertEqual(payload["qa"]["status"], "fail")
        self.assertTrue(payload["qa"]["brand_hits"])
        record = ps.save_review("sweet-potato-15s", "v1", True, decisions=[{"shot_id": "s1", "status": "flag"}], comment="ok", qa_status="fail")
        self.assertEqual(record["status"], "approved")
        self.assertEqual(ps.load_project("sweet-potato-15s")["status"], "delivered")
        exported = ps.export_version("sweet-potato-15s", "v1", preset="original", filename="final-cut")
        self.assertTrue(exported["path"].endswith("final-cut.mp4"))
        self.assertTrue((self.tmp / exported["path"]).is_file())
        self.assertEqual(len(ps.list_deliverables("sweet-potato-15s")), 1)

    def test_assets_list_probe_reuse_delete(self) -> None:
        from PIL import Image

        upload = asset_store.UPLOADS / "test.png"
        upload.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 24), "#E0338A").save(upload)
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")

        rows = asset_store.list_assets(source="upload")
        self.assertEqual(len(rows), 1)
        record = asset_store.probe(rows[0])
        self.assertEqual((record["kind"], record["width"], record["height"]), ("image", 40, 24))

        result = asset_store.reuse_asset(record["id"], "sweet-potato-15s", shot_id="s1", mode="replace")
        self.assertTrue(result["shot"]["preview"].startswith("projects/sweet-potato-15s/assets/"))
        self.assertEqual(result["shot"]["status"], "ready")
        self.assertTrue((self.tmp / result["shot"]["preview"]).is_file())

        ref = asset_store.reuse_asset(record["id"], "sweet-potato-15s", mode="reference")
        self.assertTrue(ps.load_project("sweet-potato-15s")["brief"]["reference_assets"])
        self.assertIsNotNone(ref["asset"])

        render = self.tmp / "projects" / "sweet-potato-15s" / "renders" / "fake.mp4"
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"fake")
        render_asset = next(row for row in asset_store.list_assets(source="render"))
        with self.assertRaises(ValueError):
            asset_store.delete_asset(render_asset["id"])
        # uploads are deletable
        self.assertTrue(asset_store.delete_asset(record["id"]))

    def test_trash_and_restore(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        token = ps.trash_project("sweet-potato-15s")
        self.assertEqual(ps.list_projects(), [])
        restored = ps.restore_project(token)
        self.assertEqual(restored["id"], "sweet-potato-15s")
        self.assertEqual(len(ps.project_detail("sweet-potato-15s")["current_version"]["shots"]), 3)

    def test_unknown_shot_and_bad_order(self) -> None:
        self._project(scenes=[scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")])
        ps.ensure_version("sweet-potato-15s")
        with self.assertRaises(ValueError):
            ps.reorder_shots("sweet-potato-15s", "v1", ["s1", "s2"])
        with self.assertRaises(KeyError):
            ps.delete_shot("sweet-potato-15s", "v1", "nope")


if __name__ == "__main__":
    unittest.main()
