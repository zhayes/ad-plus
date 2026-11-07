from __future__ import annotations

import unittest

from adplus.restyle import plans


class RestylePlanTest(unittest.TestCase):
    def test_default_and_patch(self) -> None:
        blueprint = {
            "groups": {
                "scenes": [{"id": "sc01"}],
                "outfits": [{"id": "of01"}],
                "objects": [{"id": "ob01"}],
            }
        }
        plan = plans.default_plan(blueprint)
        self.assertEqual(plan["revision"], 1)
        self.assertEqual(plan["scenes"]["sc01"]["mode"], "keep")
        self.assertEqual(plan["objects"]["ob01"]["mode"], "keep")

        updated = plans.apply_patch(plan, {"change_level": "all", "scenes": {"sc01": {"mode": "relight"}}}, 1)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["change_level"], "all")
        self.assertEqual(updated["scenes"]["sc01"]["mode"], "relight")

    def test_revision_conflict(self) -> None:
        plan = plans.default_plan()
        with self.assertRaises(ValueError) as ctx:
            plans.apply_patch(plan, {"change_level": "light"}, 99)
        self.assertEqual(str(ctx.exception), "revision_conflict")

    def test_unknown_field(self) -> None:
        with self.assertRaises(ValueError):
            plans.apply_patch(plans.default_plan(), {"magic": 1}, 1)


if __name__ == "__main__":
    unittest.main()
