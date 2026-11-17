from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json
from adplus import production_settings, project_store


class ProductionSettingsTest(unittest.TestCase):
    def test_defaults_are_explicit(self) -> None:
        settings = production_settings.default_settings({
            "route": {"id": "avatar_spokesperson"},
            "platform": "douyin",
            "aspect": "9:16",
            "duration_s": 15,
            "quality_tier": "standard",
        })
        self.assertEqual(settings["output"]["resolution"], "720p")
        self.assertEqual(settings["generation"]["talking_head_profile"], "wav2lip")
        self.assertEqual(settings["generation"]["broll_profile"], "seedance-2.0")
        self.assertEqual(settings["generation"]["audio_mode"], "external_tts")

    def test_merge_bumps_revision_only_when_changed(self) -> None:
        current = production_settings.default_settings({"route": {"id": "hybrid"}})
        same = production_settings.merge_settings(current, {"output": {"aspect": "9:16"}})
        self.assertEqual(same["revision"], 1)
        changed = production_settings.merge_settings(current, {"output": {"aspect": "16:9"}})
        self.assertEqual(changed["revision"], 2)

    def test_audio_change_bumps_audio_not_visual(self) -> None:
        current = production_settings.default_settings({"route": {"id": "avatar_spokesperson"}})
        changed = production_settings.merge_settings(current, {"audio": {"speed": 1.2}})
        self.assertEqual(changed["revisions"]["audio"], 2)
        self.assertEqual(changed["revisions"]["visual"], 1)

    def test_visual_change_bumps_visual_not_audio(self) -> None:
        current = production_settings.default_settings({"route": {"id": "avatar_spokesperson"}})
        changed = production_settings.merge_settings(current, {"visual": {"quality_tier": "premium"}})
        self.assertEqual(changed["revisions"]["audio"], 1)
        self.assertEqual(changed["revisions"]["visual"], 2)

    def test_legacy_v1_migrates_to_audio_visual(self) -> None:
        normalized = production_settings.normalize_settings({
            "route": {"id": "avatar_spokesperson"},
            "production_settings": {
                "revision": 4,
                "generation": {"audio_mode": "external_tts", "talking_head_profile": "seedance-2.0", "broll_profile": "seedance-2.0", "quality_tier": "draft", "budget_usd": 3},
                "voice": {"source": "persona", "override": {"provider": "local", "voice_id": "Tingting"}},
            },
        })
        self.assertEqual(normalized["schema_version"], 2)
        self.assertEqual(normalized["audio"]["mode"], "external_tts")
        self.assertEqual(normalized["audio"]["voice_id"], "Tingting")
        self.assertEqual(normalized["visual"]["talking_head_profile"], "seedance-2.0")
        self.assertEqual(normalized["budget"]["total_usd"], 3.0)

    def test_invalid_resolution_is_rejected(self) -> None:
        current = production_settings.default_settings({"route": {"id": "hybrid"}})
        with self.assertRaises(ValueError):
            production_settings.merge_settings(current, {"output": {"resolution": "8k"}})

    def test_pixel_size_and_music_mode_are_coerced(self) -> None:
        current = production_settings.default_settings({"route": {"id": "local_motion"}})
        current["output"]["resolution"] = "1080x1920"
        current["audio"]["mode"] = "music"
        normalized = production_settings.normalize_settings({
            "route": {"id": "local_motion"},
            "production_settings": current,
        })
        self.assertEqual(normalized["output"]["resolution"], "1080p")
        self.assertEqual(normalized["audio"]["mode"], "silent")

    def test_old_project_json_loads_settings(self) -> None:
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="adplus-old-project-"))
        old = project_store.PROJECTS
        project_store.PROJECTS = root / "projects"
        (project_store.PROJECTS / "old").mkdir(parents=True)
        (project_store.PROJECTS / "old" / "project.json").write_text(json.dumps({
            "title": "old", "platform": "douyin", "aspect": "9:16",
            "duration_s": 10, "quality_tier": "draft",
        }), encoding="utf-8")
        try:
            project = project_store.load_project("old")
            self.assertIsNotNone(project)
            self.assertEqual(project["production_settings"]["route_id"], "local_motion")
            self.assertEqual(project["production_settings"]["output"]["resolution"], "480p")
        finally:
            project_store.PROJECTS = old

    def test_old_project_gets_defaults_without_crashing(self) -> None:
        normalized = production_settings.normalize_settings({
            "route": {"id": "local_motion"},
            "aspect": "9:16",
            "duration_s": 10,
            "quality_tier": "draft",
        })
        self.assertEqual(normalized["route_id"], "local_motion")
        self.assertEqual(normalized["output"]["resolution"], "480p")
        self.assertEqual(normalized["generation"]["audio_mode"], "silent")
