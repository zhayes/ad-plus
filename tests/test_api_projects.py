from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from adplus import agent_bridge
from adplus import assets as asset_store
from adplus import project_store as ps
from app import config_store
from app.settings_server import app


def scene(index: int, start: float, end: float, role: str = "build") -> dict:
    return {
        "id": f"s{index}",
        "start_seconds": start,
        "end_seconds": end,
        "description": f"镜头 {index}",
        "narrative_role": role,
    }


class ProjectApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-api-"))
        self.old_projects, self.old_brands = ps.PROJECTS, ps.BRANDS
        self.old_bridge_projects = agent_bridge.PROJECTS_DIR
        self.old_uploads = asset_store.UPLOADS
        self.old_config_path = config_store._path
        config_store._path = lambda: self.tmp / "config.json"
        ps.PROJECTS = self.tmp / "projects"
        agent_bridge.PROJECTS_DIR = ps.PROJECTS
        asset_store.PROJECTS = ps.PROJECTS
        asset_store.UPLOADS = self.tmp / "uploads"
        asset_store.UPLOADS.mkdir(parents=True, exist_ok=True)
        ps.BRANDS = self.tmp / "brands"
        ps.PROJECTS.mkdir(parents=True, exist_ok=True)
        ps.create_project("红薯 · 炭火现烤 15s", project_id="sweet-potato-15s", platform="douyin")
        plan = self.tmp / "projects" / "sweet-potato-15s" / "artifacts" / "scene_plan.json"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(json.dumps({"scenes": [scene(1, 0, 2, "hook"), scene(2, 2, 5), scene(3, 5, 7.5, "cta")]}, ensure_ascii=False), encoding="utf-8")
        ps.ensure_version("sweet-potato-15s")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        ps.PROJECTS, ps.BRANDS = self.old_projects, self.old_brands
        agent_bridge.PROJECTS_DIR = self.old_bridge_projects
        asset_store.PROJECTS = self.old_projects
        asset_store.UPLOADS = self.old_uploads
        config_store._path = self.old_config_path

    def test_list_and_detail(self) -> None:
        rows = self.client.get("/api/projects")
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(rows.json()["projects"][0]["id"], "sweet-potato-15s")

        detail = self.client.get("/api/projects/sweet-potato-15s")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["current_version"]["id"], "v1")
        self.assertEqual(len(body["current_version"]["shots"]), 3)

    def test_create_project(self) -> None:
        response = self.client.post("/api/projects", json={"title": "API Ad", "project_id": "api-ad"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["id"], "api-ad")
        self.assertEqual(self.client.post("/api/projects", json={"title": "API Ad", "project_id": "api-ad"}).status_code, 409)

    def test_reorder_add_update_delete(self) -> None:
        reorder = self.client.patch(
            "/api/projects/sweet-potato-15s/versions/v1/shots/reorder",
            json={"order": ["s2", "s1", "s3"]},
        )
        self.assertEqual(reorder.status_code, 200)
        self.assertEqual([s["id"] for s in reorder.json()["version"]["shots"]], ["s2", "s1", "s3"])

        added = self.client.post(
            "/api/projects/sweet-potato-15s/versions/v1/shots",
            json={"after_id": "s1", "description": "新镜头", "duration_s": 1.5},
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(len(added.json()["version"]["shots"]), 4)

        updated = self.client.patch(
            "/api/projects/sweet-potato-15s/versions/v1/shots/s1",
            json={"duration_s": 3.5, "locked": True},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["shot"]["locked"])
        self.assertEqual(updated.json()["shot"]["duration_s"], 3.5)

        removed = self.client.delete("/api/projects/sweet-potato-15s/versions/v1/shots/s3")
        self.assertEqual(removed.status_code, 200)
        self.assertNotIn("s3", [s["id"] for s in removed.json()["version"]["shots"]])

    def test_bad_order_and_missing_shot(self) -> None:
        bad = self.client.patch(
            "/api/projects/sweet-potato-15s/versions/v1/shots/reorder",
            json={"order": ["s1"]},
        )
        self.assertEqual(bad.status_code, 400)
        missing = self.client.delete("/api/projects/sweet-potato-15s/versions/v1/shots/nope")
        self.assertEqual(missing.status_code, 404)

    def test_brands(self) -> None:
        created = self.client.post("/api/brands", json={"name": "红薯铺", "colors": ["#E0338A"], "banned_words": ["最"]})
        self.assertEqual(created.status_code, 200)
        brand = created.json()["brand"]
        self.assertTrue(brand["id"].startswith("b_"))

        patched = self.client.patch(f"/api/brands/{brand['id']}", json={"name": "红薯铺 2.0"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["brand"]["name"], "红薯铺 2.0")

        defaulted = self.client.post(f"/api/brands/{brand['id']}/default")
        self.assertEqual(defaulted.status_code, 200)
        self.assertTrue(defaulted.json()["brand"]["default"])

        applied = self.client.post(f"/api/brands/{brand['id']}/apply", json={"project_id": "sweet-potato-15s"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["project"]["brand_id"], brand["id"])

        listed = self.client.get("/api/brands")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["brands"]), 1)

        removed = self.client.delete(f"/api/brands/{brand['id']}")
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["removed"])

    def test_plan_review_export(self) -> None:
        project_dir = self.tmp / "projects" / "sweet-potato-15s"
        renders = project_dir / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "test.mp4").write_bytes(b"fake-mp4")
        ps.update_version("sweet-potato-15s", "v1", {"render": {"path": "projects/sweet-potato-15s/renders/test.mp4", "width": 1080, "height": 1920}})
        (project_dir / "artifacts" / "final_review.json").write_text(
            json.dumps({"status": "pass", "checks": {"technical_probe": {"verdict": "pass", "detail": "ok"}}, "issues_found": []}),
            encoding="utf-8",
        )
        quote_dir = project_dir / "quotes"
        quote_dir.mkdir(parents=True, exist_ok=True)
        (quote_dir / "q1.json").write_text(
            json.dumps({"id": "q1", "project_id": "sweet-potato-15s", "status": "pending", "headline": "15s 方案", "total_usd": 0.2}),
            encoding="utf-8",
        )

        plan = self.client.get("/api/projects/sweet-potato-15s/plan")
        self.assertEqual(plan.status_code, 200)
        self.assertEqual(plan.json()["quote"]["id"], "q1")

        review = self.client.get("/api/projects/sweet-potato-15s/review")
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["qa"]["status"], "pass")

        decision = self.client.post(
            "/api/projects/sweet-potato-15s/review",
            json={"version_id": "v1", "approved": True, "decisions": [{"shot_id": "s1", "status": "pass"}], "comment": "ok"},
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["detail"]["project"]["status"], "delivered")
        self.assertEqual(decision.json()["review"]["status"], "approved")

        exported = self.client.post(
            "/api/projects/sweet-potato-15s/export",
            json={"version_id": "v1", "preset": "original", "filename": "final-cut"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.json()["deliverable"]["path"].endswith("final-cut.mp4"))
        self.assertEqual(len(self.client.get("/api/projects/sweet-potato-15s/deliverables").json()["deliverables"]), 1)

    def test_quote_approval_advances_project(self) -> None:
        quote_dir = self.tmp / "projects" / "sweet-potato-15s" / "quotes"
        quote_dir.mkdir(parents=True, exist_ok=True)
        (quote_dir / "q1.json").write_text(
            json.dumps({"id": "q1", "project_id": "sweet-potato-15s", "status": "pending", "total_usd": 0.2}),
            encoding="utf-8",
        )
        result = self.client.post("/api/quotes/q1", json={"project_id": "sweet-potato-15s", "approved": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get("/api/projects/sweet-potato-15s").json()["project"]["status"], "storyboard")

    def test_review_reject_sets_producing(self) -> None:
        rejected = self.client.post(
            "/api/projects/sweet-potato-15s/review",
            json={"version_id": "v1", "approved": False, "decisions": [{"shot_id": "s1", "status": "flag"}], "comment": "太快"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["detail"]["project"]["status"], "producing")
        self.assertEqual(rejected.json()["review"]["status"], "rejected")

    def test_upload_list_reuse_delete_asset(self) -> None:
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (32, 20), "#E0338A").save(buffer, format="PNG")
        uploaded = self.client.post("/api/upload?name=asset.png", content=buffer.getvalue())
        self.assertEqual(uploaded.status_code, 200)
        asset = uploaded.json()["asset"]
        self.assertEqual(asset["kind"], "image")

        rows = self.client.get("/api/assets?source=upload")
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(len(rows.json()["assets"]), 1)

        detail = self.client.get(f"/api/assets/{asset['id']}")
        self.assertEqual(detail.json()["asset"]["width"], 32)
        self.assertEqual(detail.json()["asset"]["height"], 20)

        reused = self.client.post(
            f"/api/assets/{asset['id']}/reuse",
            json={"project_id": "sweet-potato-15s", "shot_id": "s1", "mode": "replace"},
        )
        self.assertEqual(reused.status_code, 200)
        self.assertTrue(reused.json()["shot"]["preview"].startswith("projects/sweet-potato-15s/assets/"))
        self.assertEqual(self.client.get("/api/projects/sweet-potato-15s").json()["current_version"]["shots"][0]["preview"], reused.json()["shot"]["preview"])

        removed = self.client.delete(f"/api/assets/{asset['id']}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(len(self.client.get("/api/assets?source=upload").json()["assets"]), 0)

    def test_job_retry_queues_copy(self) -> None:
        jobs_dir = self.tmp / "projects" / "sweet-potato-15s" / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        original = {
            "id": "j1", "project_id": "sweet-potato-15s", "kind": "render",
            "status": "failed", "progress": 0.4, "frames_done": 10, "frames_total": 25,
            "started_at": "2026-11-05T10:00:00+0800", "finished_at": "2026-11-05T10:01:00+0800",
            "error": "boom", "output": "/Users/chad/OpenMontage/projects/sweet-potato-15s/renders/old.mp4",
            "cancel_requested": False, "log_tail": ["fail"],
        }
        (jobs_dir / "j1.json").write_text(json.dumps(original), encoding="utf-8")
        render = self.tmp / "projects" / "sweet-potato-15s" / "renders" / "old.mp4"
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"x")
        listed = self.client.get("/api/jobs")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["jobs"][0]["id"], "j1")
        self.assertEqual(listed.json()["jobs"][0]["output"], str(render))
        response = self.client.post("/api/jobs/j1/retry", json={"project_id": "sweet-potato-15s"})
        self.assertEqual(response.status_code, 200)
        job = response.json()["job"]
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["retry_of"], "j1")
        self.assertNotEqual(job["id"], "j1")

    def test_spa_deep_links_serve_index(self) -> None:
        for path in ("/projects", "/studio/sweet-potato-15s/storyboard", "/tasks", "/assets", "/assets/brands", "/settings"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("id=\"root\"", response.text)

    def test_config_and_notify_validation(self) -> None:
        config = self.client.get("/api/config")
        self.assertEqual(config.status_code, 200)
        self.assertIn("notifications", config.json())
        saved = self.client.post("/api/config", json={"notify_done": False, "daily_budget_usd": 5})
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["notifications"]["done"])
        self.assertEqual(saved.json()["daily_budget_usd"], 5)
        self.assertEqual(self.client.post("/api/notify", json={"body": ""}).status_code, 400)

    def test_switch_version(self) -> None:
        created = self.client.post("/api/projects/sweet-potato-15s/versions", json={"label": "V2"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["version"]["id"], "v2")
        detail = self.client.get("/api/projects/sweet-potato-15s").json()
        self.assertEqual(detail["current_version"]["id"], "v2")

        switched = self.client.patch("/api/projects/sweet-potato-15s/versions/v1", json={"current": True})
        self.assertEqual(switched.status_code, 200)
        detail = self.client.get("/api/projects/sweet-potato-15s").json()
        self.assertEqual(detail["current_version"]["id"], "v1")

    def test_delete_and_restore(self) -> None:
        removed = self.client.delete("/api/projects/sweet-potato-15s")
        self.assertEqual(removed.status_code, 200)
        token = removed.json()["trash_id"]
        self.assertEqual(self.client.get("/api/projects/sweet-potato-15s").status_code, 404)
        self.assertEqual(self.client.get("/api/projects").json()["projects"], [])

        restored = self.client.post(f"/api/projects/restore/{token}")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["project"]["id"], "sweet-potato-15s")
        self.assertEqual(self.client.get("/api/projects/sweet-potato-15s").status_code, 200)

    def test_404(self) -> None:
        self.assertEqual(self.client.get("/api/projects/nope").status_code, 404)
        self.assertEqual(self.client.get("/api/brands/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()


class ProductionFlowTest(ProjectApiTest):
    def test_route_brief_proposal_script_scene_assets(self) -> None:
        project_id = "sweet-potato-15s"
        route = self.client.post(f"/api/projects/{project_id}/route", json={"route_id": "local_motion"})
        self.assertEqual(route.status_code, 200, route.text)
        self.assertEqual(route.json()["route"]["id"], "local_motion")

        brief = self.client.post(f"/api/projects/{project_id}/stages/brief/approve", json={})
        self.assertEqual(brief.status_code, 200, brief.text)
        self.assertEqual(brief.json()["current_stage"], "proposal")

        quote_dir = self.tmp / "projects" / project_id / "quotes"
        quote_dir.mkdir(parents=True, exist_ok=True)
        (quote_dir / "q1.json").write_text(json.dumps({
            "id": "q1", "project_id": project_id, "status": "approved",
            "headline": "test", "total_usd": 0, "low_usd": 0, "high_usd": 0,
            "eta_seconds": 60, "line_items": [], "assumptions": [],
        }), encoding="utf-8")
        packet = {
            "concept": {"title": "测试概念", "hook": "第一秒", "insight": "原因", "visual_approach": "画面", "core_message": "信息", "cta": "行动"},
            "script": ["0-2s 钩子", "2-15s 落版"],
            "shots": [
                {"id": "s1", "role": "hook", "duration_s": 2.2, "visual": "画面 1", "text": "钩子"},
                {"id": "s2", "role": "cta", "duration_s": 12.8, "visual": "画面 2", "text": "行动"},
            ],
            "deliverables": {"platform": "douyin", "aspect": "9:16", "duration_s": 15},
        }
        artifacts = self.tmp / "projects" / project_id / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "proposal_packet.json").write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

        production = self.client.get(f"/api/projects/{project_id}/production")
        self.assertEqual(production.status_code, 200)
        self.assertEqual(production.json()["current_stage"], "script")
        self.assertGreaterEqual(len(production.json()["shots"]), 2)

        saved = self.client.post(f"/api/projects/{project_id}/script", json={"lines": [{"text": "一句脚本"}]})
        self.assertEqual(saved.status_code, 200)
        approved = self.client.post(f"/api/projects/{project_id}/stages/script/approve", json={})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["current_stage"], "scene")

        scene = self.client.post(f"/api/projects/{project_id}/stages/scene/approve", json={})
        self.assertEqual(scene.status_code, 200, scene.text)
        self.assertEqual(scene.json()["current_stage"], "assets")

        assets = self.client.post(f"/api/projects/{project_id}/stages/assets/approve", json={})
        self.assertEqual(assets.status_code, 200, assets.text)
        self.assertEqual(assets.json()["current_stage"], "compose")

    def test_cannot_skip_stage(self) -> None:
        response = self.client.post("/api/projects/sweet-potato-15s/stages/scene/approve", json={})
        self.assertEqual(response.status_code, 400)
