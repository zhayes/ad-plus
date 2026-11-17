"""Unit tests for P1: gag extraction and script adaptation (no network)."""

from __future__ import annotations

import unittest

from adplus.recreate import gag, script


def _skeleton() -> dict:
    return {
        "source": {"duration_s": 11.04},
        "shots": [{"index": 0, "start_s": 0.0, "end_s": 2.08}, {"index": 1, "start_s": 2.08, "end_s": 11.04}],
        "cuts_s": [2.08],
        "speech": {
            "language": "zh",
            "language_probability": 0.99,
            "quality": {"status": "ok"},
            "speakers": {"labels": ["A", "A", "A", "A", "A", "B"], "confidence": 0.51},
            "segments": [{"start": 0.0, "end": 2.0, "text": "你也买这个啊"}],
        },
        "product_slot": {"names": ["袋装瓜子"], "visible_ratio": 1.0, "max_prominence": "high"},
        "text_in_frame": [],
        "beats": [
            {
                "id": "b0",
                "start_s": 0.0,
                "end_s": 2.08,
                "function": "hook",
                "speech_rate": 5.8,
                "dialogue": [{"speaker": "A", "text": "你也给你老婆买原味瓜子啊"}],
                "visual": {"action": "四人并排走来"},
            },
            {
                "id": "b1",
                "start_s": 2.08,
                "end_s": 4.3,
                "function": "setup",
                "speech_rate": 7.2,
                "dialogue": [{"speaker": "B", "text": "对啊我老婆都吃完两袋了"}],
                "visual": {"action": "站定交谈"},
            },
            {
                "id": "b2",
                "start_s": 4.3,
                "end_s": 6.02,
                "function": "escalation",
                "speech_rate": 5.8,
                "dialogue": [{"speaker": "A", "text": "你多少钱买的39块9"}],
                "visual": {"action": "举袋比价"},
            },
            {
                "id": "b5",
                "start_s": 8.9,
                "end_s": 11.04,
                "function": "punchline",
                "speech_rate": 4.7,
                "dialogue": [{"speaker": "B", "text": "那我现在就去抢"}],
                "visual": {"action": "抱袋跑出画"},
            },
        ],
    }


class GagNormalizeTest(unittest.TestCase):
    def test_unknown_mechanism_is_downgraded(self) -> None:
        spec = gag.normalize({"mechanism": "funny_vibes", "must_keep": []}, _skeleton())
        self.assertEqual(spec["mechanism"], "none")
        self.assertLessEqual(spec["confidence"], 0.35)

    def test_must_keep_ids_and_beats_are_validated(self) -> None:
        raw = {
            "mechanism": "price_compare_punchline",
            "confidence": 0.9,
            "must_keep": [
                {"text": "价格出现两次", "beat": "b2"},
                {"text": "落点有动作", "beat": "b9"},  # beat does not exist
                {"text": "", "beat": "b0"},
            ],
        }
        spec = gag.normalize(raw, _skeleton())
        self.assertEqual([item["id"] for item in spec["must_keep"]], ["m1", "m2"])
        self.assertEqual(spec["must_keep"][0]["beat"], "b2")
        self.assertIsNone(spec["must_keep"][1]["beat"])
        self.assertLessEqual(spec["confidence"], 0.35)  # only two checkable items

    def test_punchline_time_is_clamped_to_the_video(self) -> None:
        raw = {"mechanism": "snatch", "punchline_beat": "b5", "punchline_at_s": 99.0, "must_keep": []}
        spec = gag.normalize(raw, _skeleton())
        self.assertEqual(spec["timing"]["punchline_at_s"], 8.9)  # beat start, not 99

    def test_fallback_does_not_invent_a_joke_without_dialogue(self) -> None:
        skeleton = _skeleton()
        for beat in skeleton["beats"]:
            beat["dialogue"] = []
        spec = gag.fallback(skeleton)
        self.assertEqual(spec["mechanism"], "none")
        self.assertFalse(spec["transferable"])
        self.assertLess(spec["confidence"], 0.3)

    def test_plot_summary_guard(self) -> None:
        spec = {"must_keep": [{"text": "讲述了一个男人买瓜子的故事"}]}
        self.assertTrue(gag.looks_like_story_summary(spec))
        self.assertFalse(gag.looks_like_story_summary({"must_keep": [{"text": "最后 2 秒有人跑出画"}]}))


class ScriptBudgetTest(unittest.TestCase):
    def test_budget_follows_the_reference_speech_rate(self) -> None:
        budgets = script.budget(_skeleton())
        self.assertGreater(budgets["b1"]["cps"], budgets["b5"]["cps"])
        # Floor, not round: a budget that rounds up overruns the beat.
        self.assertEqual(budgets["b1"]["max_chars"], int(2.22 * 7.2))
        self.assertLessEqual(budgets["b1"]["cps"], 8.5)

    def test_fit_status_boundaries(self) -> None:
        self.assertEqual(script.fit_status(8, 10), "ok")
        self.assertEqual(script.fit_status(10, 10), "tight")
        self.assertEqual(script.fit_status(11, 10), "tight")   # within 1-char slack
        self.assertEqual(script.fit_status(13, 10), "over")

    def test_over_budget_lines_are_reported(self) -> None:
        raw = {
            "beats": [
                {"id": "b0", "lines": [{"speaker": "A", "text": "这句话明显太长了根本放不下真的塞不进"}]},
                {"id": "b1", "lines": [{"speaker": "B", "text": "短"}]},
            ]
        }
        result = script.normalize(raw, _skeleton(), {"name": "鹰嘴豆"}, script.budget(_skeleton()))
        fits = {beat["id"]: beat["fit"] for beat in result["beats"]}
        self.assertEqual(fits["b0"], "over")
        self.assertIn("b0", result["totals"]["over_budget_beats"])

    def test_speakers_collapse_to_two_roles(self) -> None:
        script_doc = {
            "beats": [
                {"id": "b0", "lines": [{"speaker": "C", "text": "一"}]},
                {"id": "b1", "lines": [{"speaker": "B", "text": "二"}]},
                {"id": "b2", "lines": [{"speaker": "C", "text": "三"}]},
            ]
        }
        script._normalize_speakers(script_doc)
        labels = [beat["lines"][0]["speaker"] for beat in script_doc["beats"]]
        self.assertEqual(labels, ["A", "B", "A"])

    def test_two_lines_in_one_beat_get_two_speakers(self) -> None:
        script_doc = {"beats": [{"id": "b2", "lines": [{"speaker": "A", "text": "多少钱"}, {"speaker": "A", "text": "39块9"}]}]}
        script._split_speakers(script_doc)
        labels = [line["speaker"] for line in script_doc["beats"][0]["lines"]]
        self.assertEqual(labels, ["A", "B"])

    def test_info_tokens_include_price_and_action(self) -> None:
        self.assertEqual(script._must_keep_tokens("你39块9买的，快去抢"), {"39", "9", "买", "抢"})


if __name__ == "__main__":
    unittest.main()


class NativeBudgetTest(unittest.TestCase):
    def test_cps_cap_shortens_the_budget_for_native_audio(self) -> None:
        skeleton = _skeleton()
        normal = script.budget(skeleton)
        capped = script.budget(skeleton, cps_cap=3.9)
        self.assertLess(capped["b1"]["cps"], normal["b1"]["cps"])
        self.assertLessEqual(capped["b1"]["max_chars"], normal["b1"]["max_chars"])

    def test_native_prompt_contains_the_line_and_forbids_extra_speakers(self) -> None:
        from adplus.recreate import render_native

        beat = {"visual": {"shot_size": "近景"}, "function": "setup"}
        prompt = render_native._prompt(beat, "你多少钱买的", style="写实")
        self.assertIn("你多少钱买的", prompt)
        self.assertIn("只有一个人说话", prompt)
        self.assertIn("不要字幕", prompt)

    def test_native_prompt_without_a_line_stays_scene_only(self) -> None:
        from adplus.recreate import render_native

        prompt = render_native._prompt({"visual": {"shot_size": "中景"}}, "", style="写实")
        self.assertNotIn("说：", prompt)
        self.assertIn("不说话", prompt)
