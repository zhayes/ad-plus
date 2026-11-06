from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from adplus import oms_tools


class ProductPlateToolTest(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp(prefix="adplus-plate-tool-"))
        self.base = base / "base.mp4"
        self.image = base / "product.png"
        self.out = base / "out.mp4"
        Image.new("RGB", (512, 512), (220, 190, 200)).save(self.image)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg not installed")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=480x854:d=2",
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.base)],
            check=True, timeout=30,
        )

    def test_registered_and_runs(self) -> None:
        self.assertEqual(oms_tools.register(), ["product_plate"])
        from tools.tool_registry import registry
        registry.discover()
        tool = registry.get("product_plate")
        self.assertIsNotNone(tool)
        assert tool is not None
        self.assertEqual(tool.estimate_cost({}), 0.0)
        result = tool.execute({
            "base_video_path": str(self.base),
            "product_image_path": str(self.image),
            "output_path": str(self.out),
            "start_s": 0,
            "end_s": 1,
        })
        self.assertTrue(result.success, result.error)
        self.assertTrue(self.out.is_file())
