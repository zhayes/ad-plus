from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus import request_probe


class RequestProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-probe-"))
        from PIL import Image
        self.image = self.tmp / "frame.png"
        Image.new("RGB", (512, 512), (200, 180, 170)).save(self.image)
        self.audio = self.tmp / "voice.wav"
        self.audio.write_bytes(b"RIFF0000WAVE")

    def test_seedance_probe_builds_480p_request_without_key(self) -> None:
        result = request_probe.probe_video(
            "seedance-2.0", prompt="product shot", duration=5, resolution="480p",
            aspect_ratio="9:16", image_path=str(self.image),
        )
        self.assertTrue(result["valid"], result["error"])
        self.assertIn("/contents/generations/tasks", result["endpoint"])
        self.assertEqual(result["checks"]["resolution"], "480p")
        self.assertEqual(result["checks"]["duration"], 5)
        self.assertTrue(result["checks"]["has_reference_image"])
        self.assertNotIn("\xff", str(result["payload"]))

    def test_kling_avatar_probe_has_image_and_audio(self) -> None:
        result = request_probe.probe_avatar(
            "kling-avatar", image_path=str(self.image), audio_path=str(self.audio),
            output_path=str(self.tmp / "out.mp4"), prompt="hello",
        )
        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["method"], "POST")
        self.assertEqual(result["checks"]["model"], None)  # payload uses no model field
        self.assertIn("image", result["payload"])
        self.assertIn("sound_file", result["payload"])

    def test_wav2lip_probe_is_local_contract(self) -> None:
        result = request_probe.probe_avatar(
            "wav2lip", image_path=str(self.image), audio_path=str(self.audio),
            output_path=str(self.tmp / "out.mp4"),
        )
        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["method"], "LOCAL")
        self.assertEqual(result["endpoint"], "local://wav2lip")
