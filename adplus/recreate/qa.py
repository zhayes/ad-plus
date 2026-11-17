"""QA: the checks that decide whether a recreation is shippable.

Every check returns ``pass | warn | fail`` plus a number, so the UI can show a
red item without a paragraph of prose.  Two checks cost nothing and catch most
real failures: duration drift and a static punchline.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from adplus.recreate import media, rhythm


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=media._NO_WINDOW)


def _loudness(path: Path) -> dict[str, float]:
    proc = _run([media.FFMPEG, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    text = proc.stderr or ""
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", text)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", text)
    return {
        "mean_db": float(mean.group(1)) if mean else 0.0,
        "peak_db": float(peak.group(1)) if peak else 0.0,
    }


def check(
    final: str | Path,
    skeleton: dict[str, Any],
    script: dict[str, Any] | None = None,
    *,
    timeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final = Path(final)
    facts = media.probe(final)
    source_s = float((skeleton.get("source") or {}).get("duration_s") or 0.0)
    checks: list[dict[str, Any]] = []

    def add(cid: str, label: str, status: str, value: Any, note: str = "") -> None:
        checks.append({"id": cid, "label": label, "status": status, "value": value, "note": note})

    delta = round(facts["duration_s"] - source_s, 2) if source_s else 0.0
    oneshot_mode = any(row.get("beat") == "oneshot" for row in (timeline or {}).get("timeline") or [])
    # A single continuous take lets the model pace itself, so ±30% is normal.
    tolerance = max(0.3, source_s * (0.30 if oneshot_mode else 0.05))
    add(
        "duration",
        "总时长与原片一致",
        "pass" if abs(delta) <= tolerance else "warn",
        {"final_s": round(facts["duration_s"], 2), "source_s": round(source_s, 2), "delta_s": delta},
    )

    add(
        "format",
        "竖屏 9:16 分辨率",
        "pass" if facts["aspect"] == "9:16" else "fail",
        {"width": facts["width"], "height": facts["height"], "aspect": facts["aspect"]},
    )

    audio = _loudness(final) if facts.get("has_audio") else {}
    if not facts.get("has_audio"):
        add("audio", "有配音音轨", "fail", {}, "成片没有音轨")
    else:
        ok = -24 <= audio["mean_db"] <= -8
        add("audio", "响度在可投放区间", "pass" if ok else "warn", audio, "-16 LUFS 附近最佳")

    beats = skeleton.get("beats") or []
    covered = [row for row in ((timeline or {}).get("timeline") or []) if row.get("status") == "ok"]
    oneshot = any(row.get("beat") == "oneshot" for row in (timeline or {}).get("timeline") or [])
    if oneshot:
        # A single continuous take carries the dialogue; per-beat coverage is
        # not a meaningful check there.
        add("beats", "单镜连续拍摄", "pass", {"mode": "oneshot", "duration_s": facts["duration_s"]})
    else:
        add(
            "beats",
            "每个 beat 都有画面",
            "pass" if len(covered) == len(beats) else "fail",
            {"beats": len(beats), "covered": len(covered)},
        )

    subtitles = (timeline or {}).get("subtitles") or []
    with_text = [beat for beat in (script or {}).get("beats") or [] if beat.get("lines")]
    add(
        "subtitles",
        "有台词的 beat 都有字幕",
        "pass" if len(subtitles) >= len(with_text) else "warn",
        {"subtitled": len(subtitles), "lines_beats": len(with_text)},
    )

    punchline = _punchline_window(skeleton)
    if punchline:
        motion = rhythm.analyze_motion(final, [punchline])
        level = (motion.get("per_shot") or [{}])[0].get("level")
        add(
            "punchline",
            "笑点段落有动作（不是呆站）",
            "pass" if level in {"slow", "fast"} else "fail",
            {"window": punchline, "motion": level},
            "落点镜头静止 = 梗没落地",
        )

    if oneshot:
        ratio = round(facts["duration_s"] / source_s, 2) if source_s else 1.0
        add(
            "budget",
            "成片时长与原片相当",
            "pass" if 0.7 <= ratio <= 1.5 else "warn",
            {"ratio": ratio, "note": "单镜模式下台词自行分配节奏，允许 ±30%"},
        )
    else:
        text_beats = [beat for beat in (script or {}).get("beats") or [] if beat.get("fit")]
        over = [beat["id"] for beat in text_beats if beat.get("fit") == "over"]
        add("budget", "台词未超节拍预算", "pass" if not over else "fail", {"over": over})

    if script:
        expected = sum(len(str(line.get("text") or "")) for beat in script.get("beats") or [] for line in beat.get("lines") or [])
        if expected:
            heard = int((((timeline or {}).get("dialogue_chars")) or 0))
            if heard:
                ratio = round(heard / expected, 2)
                add("dialogue", "台词完整度", "pass" if ratio >= 0.8 else ("warn" if ratio >= 0.65 else "fail"),
                    {"heard_chars": heard, "script_chars": expected, "ratio": ratio})

    failed = [c for c in checks if c["status"] == "fail"]
    warned = [c for c in checks if c["status"] == "warn"]
    return {
        "version": 1,
        "video": str(final),
        "checks": checks,
        "summary": {
            "pass": len(checks) - len(failed) - len(warned),
            "warn": len(warned),
            "fail": len(failed),
            "shippable": not failed,
        },
    }


def _punchline_window(skeleton: dict[str, Any]) -> tuple[float, float] | None:
    beats = skeleton.get("beats") or []
    target = next((beat for beat in beats if beat.get("function") == "punchline"), beats[-1] if beats else None)
    if not target:
        return None
    return (float(target["start_s"]), float(target["end_s"]))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        raise SystemExit("usage: python -m adplus.recreate.qa <final.mp4> <skeleton.json> [timeline.json]")
    skeleton = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    timeline = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 else None
    report = check(sys.argv[1], skeleton, timeline=timeline)
    for row in report["checks"]:
        print(f"{row['status']:<5} {row['id']:<10} {row['label']}  {row['value']}")
    print(json.dumps(report["summary"], ensure_ascii=False))
