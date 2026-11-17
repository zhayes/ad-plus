from __future__ import annotations

import unittest

from adplus.restyle import speech


class RestyleSpeechTest(unittest.TestCase):
    def test_no_speech(self) -> None:
        row = speech.classify({"speech_like": 0.0, "activity": 0.0}, {"face_visible": True, "mouth_motion": 0.0})
        self.assertEqual(row["mode"], "no_speech")

    def test_voiceover_without_face(self) -> None:
        row = speech.classify({"speech_like": 1.0, "activity": 0.3}, {"face_visible": False, "mouth_motion": 0.0})
        self.assertEqual(row["mode"], "voiceover")

    def test_on_camera(self) -> None:
        row = speech.classify(
            {"speech_like": 1.0, "activity": 0.3},
            {"face_visible": True, "face_ratio": 0.8, "mouth_motion": 0.08},
        )
        self.assertEqual(row["mode"], "on_camera")

    def test_low_face_coverage_is_unknown(self) -> None:
        row = speech.classify(
            {"speech_like": 1.0, "activity": 0.3},
            {"face_visible": True, "face_ratio": 0.3, "mouth_motion": 0.02},
        )
        self.assertEqual(row["mode"], "unknown")

    def test_visible_but_static_is_voiceover(self) -> None:
        row = speech.classify(
            {"speech_like": 1.0, "activity": 0.3},
            {"face_visible": True, "face_ratio": 0.8, "mouth_motion": 0.001},
        )
        self.assertEqual(row["mode"], "voiceover")


if __name__ == "__main__":
    unittest.main()
