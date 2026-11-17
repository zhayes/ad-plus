"""Unit tests for the recreate P0 analyser (no network, no model load)."""

from __future__ import annotations

import unittest

import numpy as np

from adplus.recreate import asr, extract, media, ocr, rhythm, vision


def _segment(start: float, end: float, text: str, speaker: str = "A") -> dict:
    return {"start": start, "end": end, "text": text, "chars": len(text), "cps": 5.0, "speaker": speaker}


class BuildBeatsTest(unittest.TestCase):
    def test_dialogue_attaches_to_the_beat_it_overlaps_most(self) -> None:
        cuts = [2.0]
        segments = [
            _segment(0.0, 1.8, "开头一句"),
            # Straddles the cut: starts in b0, spoken mostly in b1.
            _segment(1.9, 4.2, "跨切的第二句"),
        ]
        beats = extract._build_beats(11.0, cuts, segments)
        by_id = {beat["id"]: beat for beat in beats}
        self.assertEqual([line["text"] for line in by_id["b0"]["dialogue"]], ["开头一句"])
        self.assertEqual([line["text"] for line in by_id["b1"]["dialogue"]], ["跨切的第二句"])

    def test_short_beats_merge_until_the_grid_is_legible(self) -> None:
        segments = [_segment(i * 0.9, i * 0.9 + 0.7, f"第{i}句") for i in range(20)]
        beats = extract._build_beats(20.0, [], segments, max_beats=6)
        self.assertLessEqual(len(beats), 6)
        self.assertEqual([beat["id"] for beat in beats], [f"b{i}" for i in range(len(beats))])
        # No dialogue may be lost while merging.
        merged = sum(len(beat["dialogue"]) for beat in beats)
        self.assertEqual(merged, 20)

    def test_single_shot_video_gets_a_fixed_window_grid(self) -> None:
        beats = extract._build_beats(14.0, [], [], max_beats=9, window_s=3.5)
        self.assertGreaterEqual(len(beats), 3)
        self.assertAlmostEqual(beats[0]["start_s"], 0.0)
        self.assertAlmostEqual(beats[-1]["end_s"], 14.0)


class GuessFunctionsTest(unittest.TestCase):
    def test_no_dialogue_never_claims_a_punchline(self) -> None:
        beats = extract._build_beats(12.0, [4.0, 8.0], [], max_beats=9)
        extract._guess_functions(beats, [])
        self.assertEqual(beats[0]["function"], "hook")
        self.assertTrue(all(beat["function"] in {"hook", "beat"} for beat in beats))

    def test_positional_and_lexical_labels(self) -> None:
        beats = extract._build_beats(
            12.0,
            [2.0, 4.0, 6.0, 8.0],
            [
                _segment(0.2, 1.8, "你也买这个啊"),
                _segment(2.2, 3.8, "多少钱"),
                _segment(4.2, 5.8, "三十九块九"),
                _segment(6.2, 7.8, "你人傻钱多"),
                _segment(8.2, 10.5, "那我现在就去抢"),
            ],
        )
        extract._guess_functions(beats, [])
        functions = [beat["function"] for beat in beats]
        self.assertEqual(functions[0], "hook")
        self.assertEqual(functions[-1], "punchline")
        self.assertIn("escalation", functions)
        self.assertIn("insult", functions)


class RhythmTest(unittest.TestCase):
    def test_silence_detection_uses_a_minimum_length(self) -> None:
        speech = np.array([True] * 10 + [False] * 2 + [True] * 10 + [False] * 20, dtype=bool)
        gaps = rhythm._silences(speech, hop_s=0.02)
        self.assertEqual(len(gaps), 1)
        self.assertAlmostEqual(gaps[0]["len"], 0.4, places=2)

    def test_analysis_survives_a_tone_and_a_pause(self) -> None:
        sr = 16000
        tone = 0.3 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)
        audio = np.concatenate([tone, np.zeros(sr // 2), tone])
        result = rhythm.analyze_audio(audio, sr)
        self.assertGreater(result["speech_ratio"], 0.3)
        self.assertGreaterEqual(len(result["silences"]), 1)
        self.assertIn("tempo_bpm", result)


class ParseHelpersTest(unittest.TestCase):
    def test_vlm_json_survives_code_fences(self) -> None:
        payload = vision._parse_json('```json\n{"shot_size": "中景"}\n```')
        self.assertEqual(payload["shot_size"], "中景")

    def test_vlm_json_survives_prose(self) -> None:
        payload = vision._parse_json('这是结果：{"people_count": 3} 谢谢')
        self.assertEqual(payload["people_count"], 3)

    def test_ocr_drops_garbage_and_short_runs(self) -> None:
        self.assertEqual(ocr._clean("  。 "), "")
        self.assertEqual(ocr._clean("三十九块九。"), "三十九块九")

    def test_shot_ranges_are_contiguous(self) -> None:
        shots = media.shot_ranges([2.0, 5.0], 9.0)
        self.assertEqual(shots, [(0.0, 2.0), (2.0, 5.0), (5.0, 9.0)])

    def test_kmeans_splits_two_voice_groups(self) -> None:
        low, high = asr._kmeans_1d([165.0, 170.0, 172.0, 268.0, 272.0])
        self.assertLess(low, 200)
        self.assertGreater(high, 240)


class ProductSlotTest(unittest.TestCase):
    def test_visible_frames_roll_up_to_one_slot(self) -> None:
        frames = [
            {"tag": {"product": {"visible": True, "what": "袋装瓜子", "prominence": "high"}}},
            {"tag": {"product": {"visible": False, "what": None, "prominence": "low"}}},
            {"tag": {"error": "timeout"}},
        ]
        slot = extract._product_slot(frames)
        self.assertEqual(slot["status"], "observed")
        self.assertAlmostEqual(slot["visible_ratio"], 0.33, places=2)
        self.assertEqual(slot["max_prominence"], "high")


if __name__ == "__main__":
    unittest.main()
