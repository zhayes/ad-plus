from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from adplus import capabilities, personas
from app.settings_server import app


class PersonaApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-persona-api-"))
        self.old_personas = personas.PERSONAS
        self.old_state = capabilities.STATE_DIR
        personas.PERSONAS = self.tmp / "personas"
        capabilities.STATE_DIR = self.tmp / "state"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        personas.PERSONAS = self.old_personas
        capabilities.STATE_DIR = self.old_state

    def test_persona_crud(self) -> None:
        created = self.client.post(
            "/api/personas",
            json={
                "name": "测试模特",
                "kind": "photo",
                "source_path": "uploads/demo.jpg",
                "rights": {"ai_allowed": True, "consent": True},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        persona = created.json()["persona"]
        self.assertTrue(persona["rights"]["ai_allowed"])
        listed = self.client.get("/api/personas")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["personas"]), 1)
        patched = self.client.patch(
            f"/api/personas/{persona['id']}",
            json={"rights": {"ai_allowed": True, "consent": True, "commercial_use": False}},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["persona"]["name"], "测试模特")
        removed = self.client.delete(f"/api/personas/{persona['id']}")
        self.assertTrue(removed.json()["removed"])
        self.assertEqual(self.client.get("/api/personas").json()["personas"], [])

    def test_models_are_listed_with_status(self) -> None:
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        models = {item["id"]: item for item in response.json()["models"]}
        self.assertIn("seedance-2.0", models)
        self.assertIn("seedance-2.5", models)
        self.assertIn("wav2lip", models)
        self.assertIn(models["seedance-2.0"]["status"], {"available", "unconfigured", "blocked"})
