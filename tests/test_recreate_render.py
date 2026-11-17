"""Tests for P3 assembly and QA (local ffmpeg, no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus.recreate import assemble, media, qa


def _skeleton() -> dict:
    return {
        "source": {"duration_s": 4.0},
        "beats": [
            {"id": "b0", "start_s": 0.0, "end_s": 2.0, "function": "hook", "dialogue": []},
            {"id": "b1", "start_s": 2.0, "end_s": 4.0, "function": "punchline", "dialogue": []},
        ],
    }


class SlotTest(unittest.TestCase):
    def test_still_becomes_a_clip_of_the_exact_slot_length(self) -> None:
        from PIL import Image

        tmp = Path(tempfile.mkdtemp(prefix="adplus-slot-"))
        still = tmp / "still.png"
        Image.new("RGB", (240, 426), (40, 60, 90)).save(still)
        out = assemble._clip_to_slot(still, 1.5, tmp / "slot.mp4")
        self.assertTrue(out.is_file())
        self.assertAlmostEqual(media.probe(out)["duration_s"], 1.5, delta=0.15)

    def test_subtitle_card_is_transparent_and_full_frame(self) -> None:
        from PIL import Image

        tmp = Path(tempfile.mkdtemp(prefix="adplus-sub-"))
        card = assemble._subtitle_card("你人傻钱多啊", tmp / "sub.png", width=720, height=1280)
        image = Image.open(card)
        self.assertEqual(image.size, (720, 1280))
        self.assertEqual(image.mode, "RGBA")
        alpha_min, _ = image.getextrema()[3]
        self.assertEqual(alpha_min, 0)  # transparent background, text only


class QaTest(unittest.TestCase):
    def test_punchline_window_falls_back_to_last_beat(self) -> None:
        skeleton = _skeleton()
        self.assertEqual(qa._punchline_window(skeleton), (2.0, 4.0))

    def test_punchline_window_prefers_the_labelled_beat(self) -> None:
        skeleton = _skeleton()
        skeleton["beats"][0]["function"] = "punchline"
        self.assertEqual(qa._punchline_window(skeleton), (0.0, 2.0))

    def test_missing_audio_is_a_failure(self) -> None:
        import subprocess

        tmp = Path(tempfile.mkdtemp(prefix="adplus-qa-"))
        silent = tmp / "silent.mp4"
        subprocess.run(
            [media.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x568:d=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent)],
            check=True,
        )
        report = qa.check(silent, _skeleton())
        audio = next(row for row in report["checks"] if row["id"] == "audio")
        self.assertEqual(audio["status"], "fail")
        self.assertFalse(report["summary"]["shippable"])


if __name__ == "__main__":
    unittest.main()
