from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from adplus import agent_bridge
from app.settings_server import app


class ApprovalApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-approvals-"))
        self.old_bridge_projects = agent_bridge.PROJECTS_DIR
        agent_bridge.PROJECTS_DIR = self.tmp / "projects"
        agent_bridge.PROJECTS_DIR.mkdir(parents=True)
        self.client = TestClient(app)
        self.project_id = "gate-test"
        self.record_id = "a_test_1"
        agent_bridge.write_record(
            "approvals",
            self.project_id,
            {
                "id": self.record_id,
                "project_id": self.project_id,
                "stage": "scene_plan",
                "status": "pending",
                "note": "分镜待确认",
                "created_at": "2026-11-13T11:00:00+0800",
            },
        )

    def tearDown(self) -> None:
        agent_bridge.PROJECTS_DIR = self.old_bridge_projects

    def test_approve_pending_gate(self) -> None:
        """Regression: approving a gate crashed with NameError (quote_id)."""
        res = self.client.post(
            f"/api/approvals/{self.record_id}",
            json={"project_id": self.project_id, "approved": True, "comment": ""},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["approval"]["status"], "approved")
        stored = agent_bridge.read_record("approvals", self.project_id, self.record_id)
        self.assertEqual(stored["status"], "approved")

    def test_reject_pending_gate(self) -> None:
        res = self.client.post(
            f"/api/approvals/{self.record_id}",
            json={"project_id": self.project_id, "approved": False, "comment": "第二个镜头太快"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        stored = agent_bridge.read_record("approvals", self.project_id, self.record_id)
        self.assertEqual(stored["status"], "rejected")
        self.assertEqual(stored["decision"]["comment"], "第二个镜头太快")

    def test_unknown_gate_is_404(self) -> None:
        res = self.client.post(
            "/api/approvals/a_missing",
            json={"project_id": self.project_id, "approved": True},
        )
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
