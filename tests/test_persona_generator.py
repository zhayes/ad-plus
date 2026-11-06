from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import persona_generator
from tools.base_tool import ToolResult, ToolStatus


class FakeImageTool:
    def __init__(self) -> None:
        self.inputs = []

    def get_status(self):
        return ToolStatus.AVAILABLE

    def execute(self, inputs):
        self.inputs.append(inputs)
        out = Path(inputs["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        outputs = []
        for index in range(1, int(inputs.get("n", 1)) + 1):
            path = out.with_name(f"{out.stem}_{index}{out.suffix}")
            path.write_bytes(b"png")
            outputs.append(str(path))
        return ToolResult(success=True, data={"outputs": outputs}, cost_usd=0.01)


class PersonaGeneratorTest(unittest.TestCase):
    def test_generates_candidates_and_can_lock_reference(self) -> None:
        from tools.tool_registry import registry

        fake = FakeImageTool()
        root = Path(tempfile.mkdtemp(prefix="adplus-persona-gen-"))
        uploads = root / "uploads"
        uploads.mkdir()
        reference = uploads / "ref.png"
        reference.write_bytes(b"ref")
        old_uploads = persona_generator.UPLOADS
        old_discover, old_get = registry.discover, registry.get
        persona_generator.UPLOADS = uploads
        registry.discover = lambda: None
        registry.get = lambda name: fake if name == "minimax_image" else None
        try:
            result = persona_generator.generate_candidates(
                prompt="fictional presenter", count=2, reference_path=reference,
            )
        finally:
            persona_generator.UPLOADS = old_uploads
            registry.discover, registry.get = old_discover, old_get
        self.assertEqual(len(result["candidates"]), 2)
        self.assertTrue(result["reference_used"])
        self.assertEqual(result["cost_usd"], 0.01)
        self.assertEqual(fake.inputs[0]["n"], 2)
        self.assertTrue(fake.inputs[0]["subject_reference"][0]["image_file"].startswith("data:image/png;base64,"))
        self.assertTrue(all(item["path"].startswith("uploads/") for item in result["candidates"]))
