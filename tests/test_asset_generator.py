from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import asset_generator, canonical_artifacts, pipeline_runner, project_store


class AssetGeneratorTest(unittest.TestCase):
    def test_talking_head_requires_audio_before_video(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-asset-gate-"))
        old = project_store.PROJECTS
        project_store.PROJECTS = root / "projects"
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("gate", project_id="asset-gate", route={"id": "avatar_spokesperson"})
        project_store.create_version("asset-gate", "v1", copy_shots=False)
        shot = project_store.add_shot("asset-gate", "v1", description="口播", narration="台词", duration_s=3, production_method="avatar")["shots"][0]
        settings = project_store.load_project("asset-gate")["production_settings"]
        try:
            with self.assertRaisesRegex(ValueError, "配音"):
                asset_generator.generate_shot("asset-gate", shot, settings)
        finally:
            project_store.PROJECTS = old

    def test_run_writes_preview_and_assets_checkpoint(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="adplus-asset-gen-"))
        old_projects = project_store.PROJECTS
        old_canonical = canonical_artifacts.PROJECTS
        old_pipeline = pipeline_runner.PROJECTS
        old_generate = asset_generator.generate_shot
        old_update, old_finish, old_cancel = asset_generator.job_store.update, asset_generator.job_store.finish, asset_generator.job_store.cancel_requested
        project_store.PROJECTS = root / "projects"
        canonical_artifacts.PROJECTS = project_store.PROJECTS
        pipeline_runner.PROJECTS = project_store.PROJECTS
        project_store.PROJECTS.mkdir(parents=True)
        project_store.create_project("batch", project_id="batch-test", route={"id": "avatar_spokesperson"})
        project_store.create_version("batch-test", "v1", copy_shots=False)
        project_store.add_shot("batch-test", "v1", description="镜头", narration="台词", duration_s=3, persona_id="p_test")
        media = project_store.PROJECTS / "batch-test" / "renders" / "fake.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"fake")
        asset_generator.generate_shot = lambda project_id, shot, settings: {
            "path": "projects/batch-test/renders/fake.mp4", "cost_usd": 0, "profile": "fake", "audio": None,
        }
        asset_generator.job_store.update = lambda job, **fields: job
        asset_generator.job_store.finish = lambda job, status, **fields: job
        asset_generator.job_store.cancel_requested = lambda project_id, job_id: False
        job = {"id": "j1", "project_id": "batch-test", "progress": 0, "log_tail": []}
        version = project_store.load_version("batch-test", "v1")
        try:
            asset_generator._run("batch-test", job, version["shots"], False)
            version = project_store.load_version("batch-test", "v1")
            self.assertEqual(version["shots"][0]["preview"], "projects/batch-test/renders/fake.mp4")
            self.assertEqual(version["shots"][0]["status"], "ready")
            manifest = canonical_artifacts.read("batch-test", "asset_manifest")
            self.assertEqual(len(manifest["assets"]), 1)
        finally:
            project_store.PROJECTS = old_projects
            canonical_artifacts.PROJECTS = old_canonical
            pipeline_runner.PROJECTS = old_pipeline
            asset_generator.generate_shot = old_generate
            asset_generator.job_store.update, asset_generator.job_store.finish, asset_generator.job_store.cancel_requested = old_update, old_finish, old_cancel
