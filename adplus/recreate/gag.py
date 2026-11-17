"""Gag extraction: turn a beat-level skeleton into a checkable ``gag_spec``.

The point is not to describe the video.  It is to name the *mechanism* that
makes it funny, list 4–7 things that must survive the remake, and pin the
punchline to a time — so the adaptation stage has something to be measured
against.

Heuristic fallback matters: if the provider is down, we still emit a spec
(``degraded: true``, low confidence) instead of blocking the pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from adplus.recreate import llm

MECHANISMS = [
    "price_compare_punchline",
    "status_contrast",
    "misunderstanding",
    "exaggeration",
    "repetition",
    "snatch",
    "callout",
    "testimonial",
    "unboxing",
    "none",
]

MECHANISM_LABELS = {
    "price_compare_punchline": "比价 → 贬损 → 促销反转 → 动作兑现",
    "status_contrast": "身份/场合反差",
    "misunderstanding": "误会与揭穿",
    "exaggeration": "夸张放大",
    "repetition": "重复/复读变味",
    "snatch": "抢夺/动作梗",
    "callout": "立 flag 后打脸",
    "testimonial": "痛点 → 演示 → 结论",
    "unboxing": "拆 → 看 → 用",
    "none": "无明确笑点",
}

SYSTEM = "你是广告片的结构分析师。只输出 JSON，不要解释，不要 markdown。"

PROMPT = """下面是一条参考视频的拆解数据。请判断它**靠什么好笑**，并给出必须保留的东西。

{data}

输出这个 JSON（字段必须齐全）：

{{
  "mechanism": "{mechanisms}" 之一,
  "mechanism_label": "一句话中文说明机制",
  "comedy_structure": {{"setup": "铺垫", "escalation": "升级", "twist": "反转", "payoff": "收尾动作"}},
  "why_it_is_funny": ["最多 4 条，说清是反差/落差/贬损/兑现中的哪一种"],
  "must_keep": [
    {{"id": "m1", "text": "可被第三人检查的具体要求", "beat": "b0", "confidence": 0.8}}
  ],
  "may_change": ["商品", "价格", "人物", "场景", "措辞"],
  "punchline_beat": "b5 或 null",
  "punchline_at_s": 9.0,
  "performance": {{"style": "表演风格", "faces": "表情要求"}},
  "transferable": true,
  "transfer_requirements": ["换商品/换人时仍然成立的前提"],
  "risks": ["合规或执行风险"],
  "confidence": 0.0 到 1.0
}}

规则：
- must_keep 4 到 7 条，每条必须挂到一个真实存在的 beat，且能被第三个人检查。
- 不要写“要有趣”“要有梗”这类无法检查的话。
- punchline_at_s 标**动作发生**的时刻，不是台词开始。
- 没有对白、或看不出笑点时，mechanism 填 "none"，confidence 低于 0.4。
- 不要复述剧情，不要写“讲述了一个……的故事”。"""


def digest(skeleton: dict[str, Any]) -> str:
    """Compact, model-readable summary of a skeleton."""
    source = skeleton.get("source") or {}
    speech = skeleton.get("speech") or {}
    quality = (speech.get("quality") or {}).get("status", "unknown")
    speakers = (speech.get("speakers") or {})
    product = skeleton.get("product_slot") or {}
    lines = [
        f"片长 {source.get('duration_s')}s，{len(skeleton.get('shots') or [])} 个镜头，切点 {skeleton.get('cuts_s')}",
        f"人声：{speech.get('language')} 置信 {speech.get('language_probability')}，{len(speech.get('segments') or [])} 句，"
        f"说话人 {speakers.get('labels')}（置信 {(speakers.get('confidence') or 0):.2f}），质量 {quality}",
        f"商品：{product.get('names')}，可见比例 {product.get('visible_ratio')}，最高显著度 {product.get('max_prominence')}",
        f"画面文字：{(skeleton.get('text_in_frame') or [{}])[0].get('texts') if skeleton.get('text_in_frame') else '无'}",
        "节拍：",
    ]
    for beat in skeleton.get("beats") or []:
        visual = (beat.get("visual") or {})
        dialogue = " / ".join(f"[{line.get('speaker') or '?'}] {line['text']}" for line in beat.get("dialogue") or [])
        lines.append(
            f"- {beat['id']} {beat['start_s']:.1f}-{beat['end_s']:.1f}s "
            f"{beat.get('function')} 语速{beat.get('speech_rate')}字/s "
            f"画面：{visual.get('action') or '未识别'}｜台词：{dialogue or '无'}"
        )
    return "\n".join(lines)


def extract(skeleton: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    """Return a normalised gag_spec. Never raises."""
    data = digest(skeleton)
    try:
        raw = llm.chat_json(
            SYSTEM,
            PROMPT.format(data=data, mechanisms="、".join(MECHANISMS)),
            model=model,
            max_tokens=1600,
            temperature=0.2,
        )
        spec = normalize(raw, skeleton)
        spec["source"] = {"model": model or llm.MODEL, "prompt": "gag-v1", "degraded": False}
        return spec
    except Exception as exc:  # noqa: BLE001 - analysis degrades, never aborts
        spec = fallback(skeleton)
        spec["source"] = {"model": None, "prompt": "gag-v1", "degraded": True, "error": f"{type(exc).__name__}: {exc}"[:200]}
        return spec


def normalize(raw: dict[str, Any], skeleton: dict[str, Any]) -> dict[str, Any]:
    """Force the model output into the contract, dropping what cannot be verified."""
    beats = {beat["id"]: beat for beat in skeleton.get("beats") or []}
    mechanism = str(raw.get("mechanism") or "none").strip()
    if mechanism not in MECHANISMS:
        mechanism = "none"

    keep: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("must_keep") or []):
        if isinstance(item, str):
            text, beat_id, confidence = item, None, 0.5
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            beat_id = item.get("beat") if item.get("beat") in beats else None
            confidence = _clamp(item.get("confidence", 0.6))
        else:
            continue
        if not text:
            continue
        keep.append({"id": f"m{len(keep) + 1}", "text": text, "beat": beat_id, "confidence": confidence})
    keep = keep[:7]

    punchline_beat = raw.get("punchline_beat")
    if punchline_beat not in beats:
        punchline_beat = None
    punchline_at = _clamp_time(raw.get("punchline_at_s"), skeleton)
    if punchline_beat and punchline_at is None:
        punchline_at = beats[punchline_beat]["start_s"]
    if punchline_at is None and not punchline_beat:
        punchline_beat = None

    confidence = _clamp(raw.get("confidence", 0.5))
    # A spec without any checkable must_keep is not a spec.
    if len(keep) < 3:
        confidence = min(confidence, 0.35)
    if mechanism == "none":
        confidence = min(confidence, 0.35)

    structure = raw.get("comedy_structure") if isinstance(raw.get("comedy_structure"), dict) else {}
    performance = raw.get("performance") if isinstance(raw.get("performance"), dict) else {}

    return {
        "version": 1,
        "mechanism": mechanism,
        "mechanism_label": str(raw.get("mechanism_label") or MECHANISM_LABELS.get(mechanism) or ""),
        "comedy_structure": {key: str(structure.get(key) or "") for key in ("setup", "escalation", "twist", "payoff")},
        "why_it_is_funny": [str(x) for x in (raw.get("why_it_is_funny") or [])][:4],
        "must_keep": keep,
        "may_change": [str(x) for x in (raw.get("may_change") or [])][:8] or ["商品", "价格", "人物", "场景", "措辞"],
        "timing": {"punchline_beat": punchline_beat, "punchline_at_s": punchline_at},
        "performance": {"style": str(performance.get("style") or ""), "faces": str(performance.get("faces") or "")},
        "transferable": bool(raw.get("transferable", True)),
        "transfer_requirements": [str(x) for x in (raw.get("transfer_requirements") or [])][:6],
        "risks": [str(x) for x in (raw.get("risks") or [])][:6],
        "confidence": confidence,
    }


def fallback(skeleton: dict[str, Any]) -> dict[str, Any]:
    """Heuristic spec used when the LLM is unavailable.

    It can only reuse what the skeleton already labelled, so it is deliberately
    pessimistic: low confidence, and ``degraded`` is set by the caller.
    """
    beats = skeleton.get("beats") or []
    punchline = next((beat for beat in beats if beat.get("function") == "punchline"), beats[-1] if beats else None)
    keep = []
    for beat in beats:
        if beat.get("function") in {"hook", "insult", "cta"}:
            text = f"{beat['id']} 的{'开场' if beat.get('function') == 'hook' else ('贬损' if beat.get('function') == 'insult' else '行动号召')}必须保留"
            keep.append({"id": f"m{len(keep) + 1}", "text": text, "beat": beat["id"], "confidence": 0.4})
    if punchline:
        keep.append(
            {
                "id": f"m{len(keep) + 1}",
                "text": f"落点在 {punchline['start_s']:.1f}s，最后一段必须有动作",
                "beat": punchline["id"],
                "confidence": 0.4,
            }
        )
    has_speech = any(beat.get("dialogue") for beat in beats)
    return {
        "version": 1,
        "mechanism": "none" if not has_speech else "callout",
        "mechanism_label": "启发式兜底（未调用模型）",
        "comedy_structure": {"setup": "", "escalation": "", "twist": "", "payoff": ""},
        "why_it_is_funny": [],
        "must_keep": keep[:7],
        "may_change": ["商品", "价格", "人物", "场景", "措辞"],
        "timing": {
            "punchline_beat": punchline["id"] if punchline else None,
            "punchline_at_s": punchline["start_s"] if punchline else None,
        },
        "performance": {"style": "", "faces": ""},
        "transferable": has_speech,
        "transfer_requirements": [],
        "risks": ["未调用模型，机制判断不可信"],
        "confidence": 0.2,
    }


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        return round(max(low, min(high, float(value))), 2)
    except (TypeError, ValueError):
        return 0.5


def _clamp_time(value: Any, skeleton: dict[str, Any]) -> float | None:
    duration = float((skeleton.get("source") or {}).get("duration_s") or 0.0)
    try:
        t = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    if duration and not (0 <= t <= duration):
        return None
    return t


def looks_like_story_summary(spec: dict[str, Any]) -> bool:
    """Guard used by tests and the reviewer: specs must not be plot summaries."""
    pattern = re.compile(r"(讲述了|讲述的是|故事|剧情|一个人.*然后)")
    return any(pattern.search(item.get("text", "")) for item in spec.get("must_keep") or [])
