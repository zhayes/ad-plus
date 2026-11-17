from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from adplus.restyle import capabilities
from app.settings_server import app


class RestyleCapabilityTest(unittest.TestCase):
    def test_audit_reuses_existing_tools(self) -> None:
        data = capabilities.audit()
        self.assertIn("tools", data)
        self.assertTrue(data["tools"]["scene_detect"]["registered"])
        self.assertTrue(data["tools"]["video_compose"]["registered"])
        self.assertIn("video_edit_tools", data)
        self.assertIsInstance(data["gaps"], list)

    def test_endpoint(self) -> None:
        client = TestClient(app)
        try:
            response = client.get("/api/restyle/capabilities")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("summary", payload)
            self.assertIn("gaps", payload)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
