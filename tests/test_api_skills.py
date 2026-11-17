from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import skills_store
from app.settings_server import app


class SkillApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-skills-api-"))
        self.old_skills = skills_store.SKILLS_DIR
        skills_store.SKILLS_DIR = self.tmp / "skills"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        skills_store.SKILLS_DIR = self.old_skills

    def _create(self, name: str = "ad-hook", description: str = "写短视频钩子") -> dict:
        response = self.client.post(
            "/api/skills",
            json={"name": name, "description": description, "instructions": "# 钩子\n\n先给冲突。"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["skill"]

    def test_crud_round_trip(self) -> None:
        skill = self._create()
        self.assertEqual(skill["name"], "ad-hook")
        self.assertTrue(skill["valid"])
        self.assertTrue(Path(skill["path"]).is_file())
        text = Path(skill["path"]).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("description:", text)
        self.assertIn("# 钩子", text)

        listed = self.client.get("/api/skills")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["dir"], str(skills_store.SKILLS_DIR))
        self.assertEqual(len(listed.json()["skills"]), 1)

        patched = self.client.patch(
            "/api/skills/ad-hook",
            json={"description": "新描述", "instructions": "新正文"},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["skill"]["instructions"], "新正文")
        self.assertEqual(
            self.client.get("/api/skills").json()["skills"][0]["description"], "新描述"
        )

        renamed = self.client.patch("/api/skills/ad-hook", json={"name": "ad-opening"})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertFalse((skills_store.SKILLS_DIR / "ad-hook").exists())
        self.assertTrue((skills_store.SKILLS_DIR / "ad-opening" / "SKILL.md").is_file())

        removed = self.client.delete("/api/skills/ad-opening")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertTrue(removed.json()["removed"])
        self.assertEqual(self.client.get("/api/skills").json()["skills"], [])
        self.assertTrue(any((skills_store.SKILLS_DIR / ".trash").iterdir()))

    def test_rejects_bad_names(self) -> None:
        for name in ("Ad Hook", "广告", "../evil", "-bad", "a--b", ""):
            response = self.client.post(
                "/api/skills",
                json={"name": name, "description": "x", "instructions": ""},
            )
            self.assertEqual(response.status_code, 400, f"{name!r}: {response.text}")

    def test_rejects_empty_description_and_duplicate(self) -> None:
        empty = self.client.post(
            "/api/skills",
            json={"name": "ad-hook", "description": "   ", "instructions": ""},
        )
        self.assertEqual(empty.status_code, 400, empty.text)

        self._create()
        duplicate = self.client.post(
            "/api/skills",
            json={"name": "ad-hook", "description": "另一个", "instructions": ""},
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

    def test_missing_skill_is_404(self) -> None:
        self.assertEqual(
            self.client.patch("/api/skills/nope", json={"description": "x"}).status_code, 404
        )
        self.assertEqual(self.client.delete("/api/skills/nope").status_code, 404)

    def test_broken_skill_is_listed_but_invalid(self) -> None:
        broken = skills_store.SKILLS_DIR / "broken"
        broken.mkdir(parents=True)
        (broken / "SKILL.md").write_text("---\nname: broken\n---\nbody\n", encoding="utf-8")
        rows = self.client.get("/api/skills").json()["skills"]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["valid"])
        self.assertIn("description", rows[0]["error"])

    def test_edit_keeps_extra_frontmatter(self) -> None:
        skill = self._create()
        path = Path(skill["path"])
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("---\n\n", "license: MIT\n---\n\n", 1), encoding="utf-8")
        patched = self.client.patch("/api/skills/ad-hook", json={"description": "改一下"})
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertIn("license: MIT", path.read_text(encoding="utf-8"))

    def test_pi_skill_args(self) -> None:
        self.assertEqual(skills_store.pi_skill_args(), [])
        self._create()
        args = skills_store.pi_skill_args()
        self.assertEqual(args[0], "--skill")
        self.assertEqual(Path(args[1]), skills_store.SKILLS_DIR.resolve())


if __name__ == "__main__":
    unittest.main()
