from __future__ import annotations

import unittest

from adplus.quote import plan_from_brief


class QuoteSettingsTest(unittest.TestCase):
    def test_selected_profile_and_resolution_are_used(self) -> None:
        settings = {
            "revision": 2,
            "route_id": "avatar_spokesperson",
            "output": {"duration_s": 15, "aspect": "16:9", "resolution": "720p", "fps": 30},
            "generation": {
                "talking_head_profile": "wav2lip",
                "broll_profile": "seedance-2.0",
                "audio_mode": "external_tts",
                "budget_usd": 2.0,
            },
        }
        shots, render, notes = plan_from_brief("test", 9, "9:16", False, settings=settings)
        self.assertEqual(shots[0]["tool"], "lip_sync")
        self.assertEqual(render["fps"], 30)
        self.assertIn("16:9 · 30fps · 720p", notes)

    def test_broll_requires_configured_profile(self) -> None:
        settings = {
            "revision": 1,
            "route_id": "hybrid",
            "output": {"duration_s": 10, "aspect": "9:16", "resolution": "480p", "fps": 30},
            "generation": {"broll_profile": "seedance-2.0", "audio_mode": "external_tts"},
        }
        shots, _, _ = plan_from_brief("test", 10, "9:16", False, settings=settings)
        self.assertEqual(shots[0]["tool"], "seedance_ark")
        self.assertEqual(shots[0]["params"]["resolution"], "480p")
