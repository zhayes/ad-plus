"""Build ``skeleton.json`` from a reference video.

P0 scope: structure (cuts, shots), speech (transcript, speakers, tempo),
visual tags per beat, OCR, and a first-pass beat function guess.

Deliberately honest about certainty: every guess carries
``function_source: "heuristic"`` and a confidence, and nothing here claims to
have understood the joke.  Gag extraction is P1 and runs on top of this file.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from adplus.recreate import asr, media, ocr, rhythm, vision

PRICE_RE = re.compile(
    # Transcripts mix ASCII and Chinese numerals: "39块9", "三十九块九", "19.9".
    r"(\d+(?:\.\d+)?\s*(?:块|元|毛|折|万|千))"
    r"|([零一二三四五六七八九十百千万两]+\s*(?:块|元|毛|折))"
    r"|(\d+\.\d+)|(¥|￥)"
)
NEGATIVE_RE = re.compile(r"(傻|亏|贵|坑|骗|智商|冤|浪费|不值得)")
CTA_RE = re.compile(r"(下单|链接|活动|优惠|买|囤|带一个|拍|领)")


def analyze(
    video: str | Path,
    *,
    out_dir: str | Path,
    asr_model: str | None = None,
    language: str | None = None,
    max_frames: int = 8,
    with_vision: bool = True,
    with_ocr: bool = True,
    progress=None,
) -> dict[str, Any]:
    started = time.time()
    video = Path(video)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def note(message: str) -> None:
        if progress:
            progress(message)

    note("probe")
    facts = media.probe(video)
    duration = facts["duration_s"]
    cuts = media.detect_cuts(video, duration)
    shots = media.shot_ranges(cuts, duration)
    fact_ranges = [(s, e) for s, e in shots]

    speech: dict[str, Any] = {"segments": [], "language": None, "speakers": {"labels": [], "confidence": 0.0}}
    audio = None
    if facts["has_audio"]:
        note("audio")
        audio = media.audio_f32(video, 16000)
        note("asr")
        try:
            speech = asr.transcribe(video, model_size=asr_model, language=language)
        except Exception as exc:  # noqa: BLE001 - analysis degrades, never aborts
            speech = {"error": f"{type(exc).__name__}: {exc}"[:200], "segments": [], "language": None}

    note("beats")
    beats = _build_beats(duration, cuts, speech.get("segments") or [])

    frames: list[dict[str, Any]] = []
    if with_vision or with_ocr:
        note("frames")
        frames = _render_frames(video, beats, out, max_frames)

    if with_vision and frames:
        note("vision")
        tags = vision.tag_frames([(f["path"], f["context"]) for f in frames])
        for frame, tag in zip(frames, tags):
            frame["tag"] = tag

    if with_ocr and frames:
        note("ocr")
        for frame in frames[:: max(1, len(frames) // 3)]:
            frame["ocr"] = ocr.read_frame(frame["path"])

    _attach_frames(beats, frames)
    _guess_functions(beats, speech.get("segments") or [])

    audio_bed: dict[str, Any] = {}
    if audio is not None:
        note("rhythm")
        audio_bed = rhythm.analyze_audio(audio, 16000)
        audio_bed["motion"] = rhythm.analyze_motion(video, fact_ranges)

    skeleton = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 1),
        "source": {k: facts[k] for k in ("path", "duration_s", "width", "height", "fps", "aspect", "has_audio")},
        "cuts_s": cuts,
        "shots": [{"index": i, "start_s": s, "end_s": e, "len_s": round(e - s, 2)} for i, (s, e) in enumerate(fact_ranges)],
        "beats": beats,
        "speech": {
            "language": speech.get("language"),
            "language_probability": speech.get("language_probability"),
            "segments": speech.get("segments", []),
            "speakers": speech.get("speakers", {}),
            "quality": speech.get("quality"),
            "error": speech.get("error"),
        },
        "audio_bed": audio_bed,
        "product_slot": _product_slot(frames),
        "text_in_frame": _frame_texts(frames),
        "confidence": _confidence(speech, frames),
        "notes": [
            "beat.function 是启发式猜测（P0），P1 的梗抽取会覆盖它",
            "speaker 用中位基频聚类，双人对话够用，三人以上请人工校正",
        ],
    }
    (out / "skeleton.json").write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
    return skeleton


def _build_beats(
    duration: float,
    cuts: list[float],
    segments: list[dict[str, Any]],
    *,
    max_beats: int = 9,
    window_s: float = 3.5,
) -> list[dict[str, Any]]:
    boundaries = [0.0]
    for point in cuts:
        if point - boundaries[-1] >= 0.6:
            boundaries.append(round(point, 3))
    if len(boundaries) == 1 and duration > 8.0:
        # Slideshow / single-take references never produce a scene change.
        # Fixed windows still give the editor a usable beat grid.
        t = window_s
        while t < duration - 1.0:
            boundaries.append(round(t, 3))
            t += window_s
    for seg in segments:
        start = round(float(seg["start"]), 3)
        if start - boundaries[-1] >= 0.9:
            boundaries.append(start)
    boundaries = sorted({b for b in boundaries if 0 <= b < duration})
    if not boundaries or boundaries[0] > 0:
        boundaries.insert(0, 0.0)
    points = boundaries + [round(duration, 3)]

    beats: list[dict[str, Any]] = []
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if end - start < 0.35:
            continue
        lines = []
        chars = sum(len(re.sub(r"\s+", "", line["text"])) for line in lines)
        beats.append(
            {
                "id": f"b{len(beats)}",
                "start_s": round(start, 3),
                "end_s": round(end, 3),
                "len_s": round(end - start, 2),
                "function": None,
                "function_source": "heuristic",
                "function_confidence": 0.0,
                "dialogue": lines,
                "speech_rate": round(chars / max(0.3, end - start), 2),
                "visual": None,
                "frames": [],
            }
        )
    _assign_dialogue(beats, segments)
    _merge_beats(beats, max_beats)
    return beats


def _merge_beats(beats: list[dict[str, Any]], max_beats: int) -> None:
    """Fold the shortest beat into its shorter neighbour until the grid is legible.

    A 32s talking-head transcript yields one beat per line (22 of them), which
    is a transcript, not a structure.  Nine beats is what a storyboard can hold
    and still map back to the reference.
    """
    while len(beats) > max_beats:
        index = min(range(len(beats)), key=lambda i: beats[i]["len_s"])
        if index == 0:
            pair = (0, 1)
        elif index == len(beats) - 1:
            pair = (index - 1, index)
        else:
            left, right = beats[index - 1]["len_s"], beats[index + 1]["len_s"]
            pair = (index - 1, index) if left <= right else (index, index + 1)
        first, second = beats[pair[0]], beats[pair[1]]
        first["end_s"] = second["end_s"]
        first["len_s"] = round(first["end_s"] - first["start_s"], 2)
        first["dialogue"] = sorted(first["dialogue"] + second["dialogue"], key=lambda line: line["start"])
        del beats[pair[1]]
    for i, beat in enumerate(beats):
        beat["id"] = f"b{i}"
        chars = sum(len(re.sub(r"\s+", "", line["text"])) for line in beat["dialogue"])
        beat["speech_rate"] = round(chars / max(0.3, beat["end_s"] - beat["start_s"]), 2)


def _assign_dialogue(beats: list[dict[str, Any]], segments: list[dict[str, Any]]) -> None:
    """Attach each transcript line to the beat it overlaps most.

    A line that straddles a cut ("对啊..." starting at 1.88s in a 2.08s cut)
    belongs to the beat it is mostly spoken in, not the one it started in.
    """
    for seg in segments:
        start, end = float(seg["start"]), float(seg["end"])
        best, best_overlap = None, 0.0
        for beat in beats:
            overlap = min(end, beat["end_s"]) - max(start, beat["start_s"])
            if overlap > best_overlap:
                best, best_overlap = beat, overlap
        if best is None:
            continue
        best["dialogue"].append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg.get("speaker"),
                "text": seg["text"],
                "cps": seg.get("cps"),
            }
        )
    for beat in beats:
        beat["dialogue"].sort(key=lambda line: line["start"])
        chars = sum(len(re.sub(r"\s+", "", line["text"])) for line in beat["dialogue"])
        beat["speech_rate"] = round(chars / max(0.3, beat["end_s"] - beat["start_s"]), 2)


def _render_frames(video: Path, beats: list[dict[str, Any]], out: Path, max_frames: int) -> list[dict[str, Any]]:
    """One frame per beat, capped; long beats get a second frame.

    Frames are stored at 720px: the VLM downscales to 640 on its own, and OCR
    works at 720 (upscaling to 960 then back down blurs the caption stroke and
    loses glyphs).
    """
    picked: list[tuple[dict[str, Any], float]] = []
    for beat in beats:
        start, end = beat["start_s"], beat["end_s"]
        picked.append((beat, round(start + (end - start) * 0.45, 3)))
        if end - start > 4.0:
            picked.append((beat, round(end - 0.35, 3)))
    if len(picked) > max_frames:
        step = (len(picked) - 1) / (max_frames - 1)
        kept = {round(i * step) for i in range(max_frames)}
        picked = [item for i, item in enumerate(picked) if i in kept]

    frames: list[dict[str, Any]] = []
    for i, (beat, at) in enumerate(picked):
        path = out / "frames" / f"{beat['id']}_{i:02d}.jpg"
        try:
            media.extract_frame(video, at, path, width=720)
        except ValueError:
            continue
        frames.append(
            {
                "path": str(path),
                "beat_id": beat["id"],
                "at_s": at,
                "context": f"{beat['id']}，{at:.1f}s，全片 {len(beats)} 个 beat 中的第 {beats.index(beat) + 1} 个",
            }
        )
    return frames


def _attach_frames(beats: list[dict[str, Any]], frames: list[dict[str, Any]]) -> None:
    for frame in frames:
        beat = next((b for b in beats if b["id"] == frame["beat_id"]), None)
        if beat is None:
            continue
        beat["frames"].append({"at_s": frame["at_s"], "path": frame["path"], "tag": frame.get("tag")})
        if beat["visual"] is None and frame.get("tag") and "error" not in frame["tag"]:
            beat["visual"] = frame["tag"]


def _guess_functions(beats: list[dict[str, Any]], segments: list[dict[str, Any]]) -> None:
    """Heuristic labels only — P1 replaces these with a gag-aware pass.

    Three regimes:
    * no dialogue at all -> neutral beats; never claim a punchline on a video
      we could not hear (music-only references are common);
    * dialogue -> positional labels (opening hook, last beat punchline) plus
      lexical hints (price -> escalation, insult -> insult, CTA -> cta).

    Position wins over speed: the fastest line is only used to raise the last
    beat's confidence, never to move the label elsewhere (that produced two
    punchlines in an early run).
    """
    if not beats:
        return
    has_dialogue = any(beat["dialogue"] for beat in beats)
    if not has_dialogue:
        for index, beat in enumerate(beats):
            beat["function"] = "hook" if index == 0 else "beat"
            beat["function_confidence"] = 0.3
            beat["function_source"] = "heuristic:no-dialogue"
        return

    fastest = max((b.get("speech_rate") or 0.0) for b in beats)
    for index, beat in enumerate(beats):
        text = "".join(line["text"] for line in beat["dialogue"])
        if index == 0:
            beat["function"], beat["function_confidence"] = "hook", 0.55
        elif index == len(beats) - 1:
            confidence = 0.45
            if abs((beat.get("speech_rate") or 0.0) - fastest) < 0.01:
                confidence += 0.15
            beat["function"], beat["function_confidence"] = "punchline", round(confidence, 2)
        elif NEGATIVE_RE.search(text):
            beat["function"], beat["function_confidence"] = "insult", 0.55
        elif PRICE_RE.search(text):
            beat["function"], beat["function_confidence"] = "escalation", 0.55
        elif CTA_RE.search(text):
            beat["function"], beat["function_confidence"] = "cta", 0.5
        else:
            beat["function"], beat["function_confidence"] = "setup", 0.4


def _product_slot(frames: list[dict[str, Any]]) -> dict[str, Any]:
    visible = [f for f in frames if (f.get("tag") or {}).get("product", {}).get("visible") and "error" not in (f.get("tag") or {})]
    if not frames:
        return {"status": "unknown", "visible_ratio": 0.0}
    names = [
        str(f["tag"]["product"].get("what"))
        for f in visible
        if (f.get("tag") or {}).get("product", {}).get("what")
    ]
    prominence = [str((f.get("tag") or {}).get("product", {}).get("prominence") or "") for f in visible]
    return {
        "status": "observed" if visible else "not_seen",
        "visible_ratio": round(len(visible) / len(frames), 2),
        "names": sorted({n for n in names if n and n != "None"})[:4],
        "max_prominence": "high" if "high" in prominence else ("medium" if "medium" in prominence else "low"),
    }


def _frame_texts(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for frame in frames:
        result = frame.get("ocr") or {}
        if result.get("texts"):
            out.append({"at_s": frame["at_s"], "texts": result["texts"], "regions": {k: [l["text"] for l in v] for k, v in (result.get("regions") or {}).items() if v}})
    return out


def _confidence(speech: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
    tagged = [f for f in frames if f.get("tag") and "error" not in (f.get("tag") or {})]
    return {
        "asr": speech.get("language_probability"),
        "segments": len(speech.get("segments") or []),
        "vision_frames": len(tagged),
        "vision_coverage": round(len(tagged) / len(frames), 2) if frames else 0.0,
        "speakers": (speech.get("speakers") or {}).get("confidence"),
    }
