from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import audio_generator, canonical_artifacts, project_store


class AudioGeneratorTest(unittest.TestCase):
    def test_synthesize_shot_writes_audio_only(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-audio-"))
        old_projects = project_store.PROJECTS
        old_canonical = canonical_artifacts.PROJECTS
        old_tts = audio_generator.tts.synthesize
        project_store.PROJECTS = root / "projects"
        canonical_artifacts.PROJECTS = project_store.PROJECTS
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("audio", project_id="audio-test", route={"id": "avatar_spokesperson"})
        project_store.create_version("audio-test", "v1", copy_shots=False)
        project_store.add_shot("audio-test", "v1", description="口播", narration="夏天穿背心", duration_s=3)
        audio_generator.tts.synthesize = lambda text, output, **kwargs: (
            Path(output).write_bytes(b"RIFFfake") or {"path": str(output)}
        )

        def fake_synth(text, output, **kwargs):
            Path(output).write_bytes(b"RIFFfake")
            return {"path": str(output)}

        audio_generator.tts.synthesize = fake_synth
        try:
            version = project_store.load_version("audio-test", "v1")
            settings = project_store.load_project("audio-test")["production_settings"]
            result = audio_generator.synthesize_shot("audio-test", version["shots"][0], settings)
            self.assertEqual(result["status"], "ready")
            self.assertTrue(Path(project_store.PROJECTS.parent / result["path"]).is_file())
            self.assertFalse(version["shots"][0].get("preview"))
        finally:
            project_store.PROJECTS = old_projects
            canonical_artifacts.PROJECTS = old_canonical
            audio_generator.tts.synthesize = old_tts

    def test_batch_run_writes_audio_manifest(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-audio-run-"))
        old_projects = project_store.PROJECTS
        old_canonical = canonical_artifacts.PROJECTS
        old_tts = audio_generator.tts.synthesize
        old_update, old_finish, old_cancel = audio_generator.job_store.update, audio_generator.job_store.finish, audio_generator.job_store.cancel_requested
        project_store.PROJECTS = root / "projects"
        canonical_artifacts.PROJECTS = project_store.PROJECTS
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("audio", project_id="audio-run", route={"id": "avatar_spokesperson"})
        project_store.create_version("audio-run", "v1", copy_shots=False)
        project_store.add_shot("audio-run", "v1", description="口播", narration="这是一句测试台词", duration_s=3, production_method="avatar")
        def fake_synth(text, output, **kwargs):
            Path(output).write_bytes(b"RIFFfake")
            return {"path": str(output)}
        audio_generator.tts.synthesize = fake_synth
        audio_generator.job_store.update = lambda job, **fields: job
        audio_generator.job_store.finish = lambda job, status, **fields: job
        audio_generator.job_store.cancel_requested = lambda project_id, job_id: False
        try:
            version = project_store.load_version("audio-run", "v1")
            job = {"id": "j1", "project_id": "audio-run", "log_tail": []}
            audio_generator._run("audio-run", job, version["shots"], False)
            version = project_store.load_version("audio-run", "v1")
            self.assertEqual(version["shots"][0]["audio"]["status"], "ready")
            manifest = canonical_artifacts.read("audio-run", "audio_manifest")
            self.assertEqual(len(manifest["tracks"]), 1)
        finally:
            project_store.PROJECTS = old_projects
            canonical_artifacts.PROJECTS = old_canonical
            audio_generator.tts.synthesize = old_tts
            audio_generator.job_store.update, audio_generator.job_store.finish, audio_generator.job_store.cancel_requested = old_update, old_finish, old_cancel

    def test_silent_shot_skips_tts(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-audio-silent-"))
        old_projects = project_store.PROJECTS
        project_store.PROJECTS = root / "projects"
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("audio", project_id="silent-test", route={"id": "local_motion"})
        project_store.create_version("silent-test", "v1", copy_shots=False)
        shot = project_store.add_shot("silent-test", "v1", description="broll", duration_s=3)["shots"][0]
        settings = project_store.load_project("silent-test")["production_settings"]
        try:
            result = audio_generator.synthesize_shot("silent-test", shot, settings)
            self.assertEqual(result["status"], "not_required")
            self.assertIsNone(result["path"])
        finally:
            project_store.PROJECTS = old_projects
