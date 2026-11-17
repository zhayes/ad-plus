"""Script adaptation: same beat grid, new product, same joke.

Two rules drive everything:

* **Timing budget** — Mandarin ad voiceover runs ~5.5 characters/second.  A
  line that overruns its beat is marked ``tight``/``over`` instead of being
  silently accepted, because the editor will otherwise discover it at TTS
  time.
* **Mechanism preservation** — the punchline mechanism comes from
  ``gag_spec.must_keep``; the model may change product, price, wording, people
  and setting, but every ``must_keep`` item must map to a beat.

The fallback keeps the original lines (with the product swapped) and marks the
result degraded, so a provider outage still yields something reviewable.
"""

from __future__ import annotations

import re
from typing import Any

from adplus.recreate import llm

CHARS_PER_SECOND = 5.5

SYSTEM = "你是中文广告编剧。只输出 JSON，不要解释，不要 markdown。"

PROMPT = """把这条参考片的台词改写成新产品版本。结构、节拍、笑点机制都不能变。

## 原片节拍
{beats}

## 必须保留（来自 gag_spec）
{must_keep}

## 新产品
{product}

## 硬规则
1. 节拍时长不变。一个 beat 内如果原片有两个人说话（比如“你多少钱买的？”+“39块9”），
   必须保留两句、保持先后顺序；整个 beat 的字数合计不超过预算（= 时长 × 该 beat 语速）。
2. 保留原片的信息点：原片有第二个价格数字才写，没有就只保留“正在做活动”。用占位价，不要编品牌。
3. 保留换手：原片 A 问 B 答就保持 A/B。
4. 落点句的动词必须与原片一致（原片说“抢”就写“抢”），不要换成“囤/买/拿”这类没有动作感的词。
5. 角色靠对白逻辑推断，不看原片的说话人标签（标签只是机器聚类，可能是错的）：
   - 提问（“多少钱”“你也…啊”）→ 提问者 A
   - 回答（“对啊”“39块9”“现在做活动”）→ 被问者 B
   - 吐槽（“人傻钱多”）→ 提问者 A
   - 落点（“那我现在就去抢”）→ 吐槽者 A（说完就动手，抢的是 B 的袋子）
   全程只允许 A、B 两个角色。
6. 每句尽量用满该 beat 预算的 85%–100%，不要写得太短，否则整条会短于原片。
7. 不要出现“讲述”“剧情”“故事”这类描述，只写台词。

输出 JSON：

{{
  "beats": [
    {{"id": "b0", "lines": [{{"speaker": "A", "text": "台词"}}], "shot": "一句话画面（只写动作）"}}
  ],
  "must_keep_map": {{"m1": "b0", "m2": "b5"}},
  "subtitle_lines": [{{"beat": "b0", "text": "字幕文本"}}],
  "compliance_flags": ["价格需替换为真实活动价"]
}}"""


def budget(skeleton: dict[str, Any], *, cps_cap: float | None = None) -> dict[str, dict[str, Any]]:
    """Per-beat character budget derived from how fast the reference speaks.

    A flat 5.5 chars/s punishes references that are genuinely fast (the sample
    ad delivers 7.2 chars/s in one beat).  Using the measured rate keeps the
    adaptation as dense as the original instead of forcing slower speech.
    """
    out: dict[str, dict[str, Any]] = {}
    for beat in skeleton.get("beats") or []:
        length = float(beat.get("end_s", 0)) - float(beat.get("start_s", 0))
        cps = _clamp(beat.get("speech_rate") or CHARS_PER_SECOND, 4.5, 8.5)
        # Native-audio models speak at a natural pace (~3.6-4.0 chars/s); a
        # budget computed from a fast reference produces lines that get cut.
        if cps_cap:
            cps = min(cps, float(cps_cap))
        out[beat["id"]] = {
            "len_s": round(length, 2),
            "cps": round(cps, 2),
            "max_chars": max(2, int(length * cps)),
            "function": beat.get("function"),
            "original": [line.get("text", "") for line in beat.get("dialogue") or []],
        }
    return out


def adapt(
    skeleton: dict[str, Any],
    gag: dict[str, Any],
    product: dict[str, Any],
    *,
    model: str | None = None,
    cps_cap: float | None = None,
) -> dict[str, Any]:
    """Return a validated script. Never raises."""
    budgets = budget(skeleton, cps_cap=cps_cap)
    try:
        raw = llm.chat_json(
            SYSTEM,
            PROMPT.format(
                beats=_beats_block(skeleton, budgets),
                must_keep="\n".join(f"- {item['id']}: {item['text']}（beat {item.get('beat') or '不限'}）" for item in gag.get("must_keep") or []),
                product=_product_block(product),
            ),
            model=model,
            max_tokens=2200,
            temperature=0.4,
        )
        script = normalize(raw, skeleton, product, budgets)
        _normalize_speakers(script)
        _split_speakers(script)
        _enforce_speakers(script, skeleton)
        script = _repair_over(script, budgets, model=model)
        script["source"] = {"model": model or llm.MODEL, "prompt": "script-v1", "degraded": False}
        return script
    except Exception as exc:  # noqa: BLE001
        script = fallback(skeleton, product, budgets)
        script["source"] = {"model": None, "prompt": "script-v1", "degraded": True, "error": f"{type(exc).__name__}: {exc}"[:200]}
        return script


def normalize(
    raw: dict[str, Any],
    skeleton: dict[str, Any],
    product: dict[str, Any],
    budgets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(item.get("id")): item for item in raw.get("beats") or [] if isinstance(item, dict)}
    beats: list[dict[str, Any]] = []
    for beat_id, meta in budgets.items():
        source = by_id.get(beat_id) or {}
        lines = []
        for line in source.get("lines") or []:
            text = re.sub(r"\s+", "", str((line or {}).get("text") or ""))
            if not text:
                continue
            lines.append(
                {
                    "speaker": str((line or {}).get("speaker") or "A")[:2],
                    "text": text,
                    "chars": len(text),
                }
            )
        chars = sum(line["chars"] for line in lines)
        est = round(chars / meta["cps"], 2)
        beats.append(
            {
                "id": beat_id,
                "function": meta["function"],
                "len_s": meta["len_s"],
                "cps": meta["cps"],
                "max_chars": meta["max_chars"],
                "chars": chars,
                "est_s": est,
                "fit": fit_status(chars, meta["max_chars"], est_s=est, beat_len=meta["len_s"]),
                "lines": lines,
                "shot": str(source.get("shot") or ""),
                "original": meta["original"],
            }
        )

    total_est = round(sum(beat["est_s"] for beat in beats), 2)
    digits = sorted({d for beat in beats for line in beat["lines"] for d in DIGIT_RE.findall(line["text"])})
    duration = float((skeleton.get("source") or {}).get("duration_s") or 0.0)
    flags = [str(x) for x in (raw.get("compliance_flags") or [])]
    if product.get("price") or product.get("promo_price"):
        flags.append("价格与活动价必须真实可举证，当前为占位")

    return {
        "version": 1,
        "product": {
            "name": str(product.get("name") or ""),
            "price": product.get("price"),
            "promo_price": product.get("promo_price"),
        },
        "beats": beats,
        "must_keep_map": {str(k): str(v) for k, v in (raw.get("must_keep_map") or {}).items()},
        "subtitle_lines": [
            {"beat": str(x.get("beat") or ""), "text": str(x.get("text") or "")}
            for x in (raw.get("subtitle_lines") or [])
            if isinstance(x, dict) and x.get("text")
        ],
        "totals": {
            "est_s": total_est,
            "source_s": round(duration, 2),
            "delta_s": round(total_est - duration, 2),
            "over_budget_beats": [beat["id"] for beat in beats if beat["fit"] == "over"],
            "tight_beats": [beat["id"] for beat in beats if beat["fit"] == "tight"],
            "digits": digits,
        },
        "compliance_flags": _dedupe(flags),
    }


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return CHARS_PER_SECOND


def fit_status(chars: int, max_chars: int, *, est_s: float = 0.0, beat_len: float = 0.0) -> str:
    """ok / tight / over, measured in characters against the beat budget.

    Character count is the actionable number for an editor ("删两个字"), while
    seconds are only an estimate.  ``est_s``/``beat_len`` stay in the signature
    for call sites that want to display the timing.
    """
    if max_chars <= 0:
        return "over"
    if chars <= max_chars * 0.9:
        return "ok"
    # One character of slack: TTS absorbs ~0.2s without sounding rushed, and
    # flagging 30/29 as a failure trains the user to ignore the warning.
    tolerance = max(1, max_chars // 20)
    if chars <= max_chars + tolerance:
        return "tight"
    return "over"


def fallback(skeleton: dict[str, Any], product: dict[str, Any], budgets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Keep the original lines, swap the product name — reviewable, not good."""
    name = str(product.get("name") or "").strip()
    beats: list[dict[str, Any]] = []
    for beat in skeleton.get("beats") or []:
        lines = []
        for line in beat.get("dialogue") or []:
            text = re.sub(r"\s+", "", line.get("text", ""))
            for original in ("原味瓜子", "瓜子", "泡脚桶"):
                if name and original in text:
                    text = text.replace(original, name)
            if text:
                lines.append({"speaker": str(line.get("speaker") or "A")[:2], "text": text, "chars": len(text)})
        chars = sum(line["chars"] for line in lines)
        cps = budgets[beat["id"]]["cps"]
        est = round(chars / cps, 2)
        beat_len = float(beat.get("end_s", 0)) - float(beat.get("start_s", 0))
        beats.append(
            {
                "id": beat["id"],
                "function": beat.get("function"),
                "len_s": round(beat_len, 2),
                "cps": cps,
                "max_chars": budgets[beat["id"]]["max_chars"],
                "chars": chars,
                "est_s": est,
                "fit": fit_status(chars, budgets[beat["id"]]["max_chars"], est_s=est, beat_len=beat_len),
                "lines": lines,
                "shot": (beat.get("visual") or {}).get("action") or "",
                "original": budgets[beat["id"]]["original"],
            }
        )
    total = round(sum(b["est_s"] for b in beats), 2)
    duration = float((skeleton.get("source") or {}).get("duration_s") or 0.0)
    return {
        "version": 1,
        "product": {"name": name, "price": product.get("price"), "promo_price": product.get("promo_price")},
        "beats": beats,
        "must_keep_map": {},
        "subtitle_lines": [{"beat": b["id"], "text": " / ".join(line["text"] for line in b["lines"])} for b in beats if b["lines"]],
        "totals": {
            "est_s": total,
            "source_s": round(duration, 2),
            "delta_s": round(total - duration, 2),
            "over_budget_beats": [b["id"] for b in beats if b["fit"] == "over"],
            "tight_beats": [b["id"] for b in beats if b["fit"] == "tight"],
        },
        "compliance_flags": ["未调用模型：台词沿用原片，仅替换商品名"],
    }


REPAIR_PROMPT = """这一句台词超出了节拍预算，请压缩。

节拍：{beat_id}，时长 {len_s}s，语速上限 {cps} 字/秒，最多 {max_chars} 字。
现在：{text}（{chars} 字）
功能：{function}

要求：
- 保留说话人 {speaker} 和这句话的信息点；
- **不得删除数字和动作词**（{keep_tokens}），只能压缩多余的修饰；
- 不超过 {max_chars} 字；
- 只输出 JSON：{{"lines": [{{"speaker": "{speaker}", "text": "新台词"}}]}}
"""


def _repair_over(script: dict[str, Any], budgets: dict[str, dict[str, Any]], *, model: str | None = None) -> dict[str, Any]:
    """Ask for a shorter rewrite of over-budget beats (max 3 per run).

    The model reliably ignores a character cap on the first pass but honours it
    when the single offending line is quoted back with its own budget.
    """
    repaired = 0
    for beat in script.get("beats") or []:
        if beat.get("fit") != "over" or repaired >= 3:
            continue
        meta = budgets.get(beat["id"]) or {}
        text = " / ".join(line["text"] for line in beat.get("lines") or [])
        speaker = (beat.get("lines") or [{}])[0].get("speaker") or "A"
        try:
            raw = llm.chat_json(
                SYSTEM,
                REPAIR_PROMPT.format(
                    beat_id=beat["id"],
                    len_s=meta.get("len_s"),
                    cps=meta.get("cps"),
                    max_chars=beat["max_chars"],
                    text=text,
                    chars=beat["chars"],
                    function=beat.get("function"),
                    speaker=speaker,
                    keep_tokens="、".join(sorted(_must_keep_tokens(text))) or "无",
                ),
                model=model,
                max_tokens=300,
                temperature=0.3,
            )
        except Exception:  # noqa: BLE001 - a failed repair keeps the original line
            continue
        lines = []
        for line in raw.get("lines") or []:
            value = re.sub(r"\s+", "", str((line or {}).get("text") or ""))
            if value:
                lines.append({"speaker": str((line or {}).get("speaker") or speaker)[:2], "text": value, "chars": len(value)})
        if not lines:
            continue
        chars = sum(line["chars"] for line in lines)
        if chars >= beat["chars"] or chars > beat["max_chars"]:
            continue
        # Never let compression delete the price.  A shortened line that drops
        # "39块9" is worse than an over-budget line.
        required = _must_keep_tokens(text)
        after = _must_keep_tokens(" ".join(line["text"] for line in lines))
        if not required.issubset(after):
            continue
        # Compression must not delete a turn: if the reference had two lines
        # here, the rewrite needs two lines too.
        if len(lines) < min(2, len(beat.get("original") or [])):
            continue
        beat["lines"] = lines
        beat["chars"] = chars
        beat["est_s"] = round(chars / meta["cps"], 2) if meta.get("cps") else beat["est_s"]
        beat["fit"] = fit_status(chars, beat["max_chars"], est_s=beat["est_s"], beat_len=meta.get("len_s", 0))
        repaired += 1

    total = round(sum(beat["est_s"] for beat in script.get("beats") or []), 2)
    totals = script.setdefault("totals", {})
    totals["est_s"] = total
    totals["delta_s"] = round(total - float(totals.get("source_s") or 0), 2)
    totals["over_budget_beats"] = [b["id"] for b in script.get("beats") or [] if b.get("fit") == "over"]
    totals["tight_beats"] = [b["id"] for b in script.get("beats") or [] if b.get("fit") == "tight"]
    totals["repaired"] = repaired
    collapsed = [
        beat["id"]
        for beat in script.get("beats") or []
        if len(beat.get("original") or []) >= 2 and len(beat.get("lines") or []) < 2
    ]
    totals["collapsed_beats"] = collapsed
    return script


def _split_speakers(script: dict[str, Any]) -> None:
    """Inside one beat, two lines must be two different speakers."""
    for beat in script.get("beats") or []:
        lines = beat.get("lines") or []
        if len(lines) < 2:
            continue
        if len({line["speaker"] for line in lines}) == 1:
            for index, line in enumerate(lines):
                line["speaker"] = "A" if index % 2 == 0 else "B"


def _normalize_speakers(script: dict[str, Any]) -> None:
    """Collapse speaker labels to exactly A/B, in order of first appearance.

    The model occasionally invents a third role ("C") or reuses lowercase; a
    two-person ad cannot have three speakers, and a stray label breaks the
    per-speaker voice mapping downstream.
    """
    mapping: dict[str, str] = {}
    for beat in script.get("beats") or []:
        for line in beat.get("lines") or []:
            label = str(line.get("speaker") or "A").strip()[:1].upper() or "A"
            if label not in mapping:
                mapping[label] = "A" if not mapping else ("B" if len(mapping) == 1 else "B")
            line["speaker"] = mapping[label]


def _enforce_speakers(script: dict[str, Any], skeleton: dict[str, Any]) -> None:
    """Keep the reference's turn-taking when a beat has a single speaker.

    The model swapped who delivers the insult ("你人傻钱多啊" moved from the
    asker to the answered), which breaks the A-asks/B-answers rhythm that the
    gag depends on.
    """
    confidence = float(((skeleton.get("speech") or {}).get("speakers") or {}).get("confidence") or 0.0)
    # Speaker clustering is a heuristic; below 0.7 it is more likely to be
    # wrong than the model's reading of the dialogue ("对啊"/"多少钱买的").
    if confidence < 0.7:
        return
    labels = {
        line.get("speaker")
        for beat in skeleton.get("beats") or []
        for line in beat.get("dialogue") or []
        if line.get("speaker")
    }
    if len(labels) < 2:
        return
    for beat in skeleton.get("beats") or []:
        speakers = {line.get("speaker") for line in beat.get("dialogue") or [] if line.get("speaker")}
        if len(speakers) != 1:
            continue
        original = next(iter(speakers))
        target = next((b for b in script.get("beats") or [] if b["id"] == beat["id"]), None)
        if target and len(target.get("lines") or []) == 1 and target["lines"][0]["speaker"] != original:
            target["lines"][0]["speaker"] = original


DIGIT_RE = re.compile(r"\d+")
KEEP_WORDS = ("抢", "囤", "搬", "带", "买")


def _must_keep_tokens(text: str) -> set[str]:
    tokens = set(DIGIT_RE.findall(text or ""))
    tokens.update(word for word in KEEP_WORDS if word in (text or ""))
    return tokens


def _beats_block(skeleton: dict[str, Any], budgets: dict[str, dict[str, Any]]) -> str:
    rows = []
    for beat in skeleton.get("beats") or []:
        meta = budgets[beat["id"]]
        # Speaker labels are deliberately omitted: the ASR clustering is a
        # heuristic and feeding it back anchors the model on the wrong roles.
        dialogue = beat.get("dialogue") or []
        lines = " ／ ".join(line["text"] for line in dialogue)
        count = len(dialogue)
        shape = f"（{count} 句，保持句数与顺序）" if count > 1 else ""
        rows.append(
            f"- {beat['id']} {meta['len_s']}s，上限 {meta['max_chars']} 字，功能 {meta['function']}{shape}：{lines or '无台词'}"
        )
    return "\n".join(rows)


def _product_block(product: dict[str, Any]) -> str:
    points = "、".join(str(x) for x in product.get("selling_points") or [])
    brief = str(product.get("brief") or "").strip()
    text = (
        f"名称：{product.get('name')}；品类：{product.get('category') or '未填'}；"
        f"原价占位：{product.get('price') or '未填'}；活动价占位：{product.get('promo_price') or '未填'}；"
        f"卖点：{points or '未填'}；语气：{product.get('tone') or '生活化'}"
    )
    if brief:
        text += f"；用户原话：{brief[:300]}"
    return text


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
