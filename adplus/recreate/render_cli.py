"""Per-shot rendering: keyframe -> clip, with a still fallback.

``--mode video`` calls MiniMax-H3 (image-to-video, 4s minimum, trimmed later by
the assembler).  ``--mode still`` skips generation entirely and turns each
keyframe into a still slot — that is how the pipeline is exercised before
spending on video credits, and what the UI shows as a "dry run".
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

from adplus.paths import VENDOR
from adplus.recreate import media


def _ensure_env() -> None:
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    if not os.environ.get("MINIMAX_API_KEY"):
        try:
            from app import secrets_store

            for key, value in secrets_store.merged_env().items():
                os.environ.setdefault(key, value)
        except Exception:  # noqa: BLE001
            pass


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _video_tool():
    _ensure_env()
    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get("minimax_video")
    if tool is None:
        raise RuntimeError("minimax_video 未注册")
    return tool


def render(
    skeleton: dict[str, Any],
    board: dict[str, Any],
    script: dict[str, Any] | None,
    out_dir: str | Path,
    *,
    mode: str = "video",
    model: str = "MiniMax-H3",
    max_seconds: int = 6,
    only: list[str] | None = None,
    resolution: str | None = None,
    seconds: int | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    (out / "shots").mkdir(parents=True, exist_ok=True)
    keyframes = {item["beat"]: item.get("chosen") for item in board.get("items") or []}
    script_beats = {beat["id"]: beat for beat in (script or {}).get("beats") or []}
    tool = _video_tool() if mode == "video" else None

    shots: dict[str, Any] = {}
    for beat in skeleton.get("beats") or []:
        beat_id = beat["id"]
        if only and beat_id not in only:
            continue
        keyframe = keyframes.get(beat_id)
        beat_len = float(beat["end_s"]) - float(beat["start_s"])
        record: dict[str, Any] = {
            "beat": beat_id,
            "slot_s": round(beat_len, 2),
            "keyframe": keyframe,
        }
        if mode != "video" or not keyframe:
            record.update({"mode": "still", "image": keyframe, "status": "ok" if keyframe else "no-keyframe"})
            shots[beat_id] = record
            continue

        target = out / "shots" / f"{beat_id}.mp4"
        prompt = _shot_prompt(beat, script_beats.get(beat_id))
        # H3 is 2K-only and accepts 4-15s; the Hailuo family takes 768P/1080P
        # and only 6s or 10s.  The slot trim happens later either way.
        is_h3 = model == "MiniMax-H3"
        shot_resolution = resolution or ("2K" if is_h3 else "768P")
        if seconds:
            shot_duration = int(seconds)
        elif is_h3:
            shot_duration = max(4, min(15, int(-(-beat_len // 1)) or 4))
        else:
            shot_duration = 6
        try:
            result = tool.execute(
                {
                    "prompt": prompt,
                    "operation": "image_to_video",
                    "model": model,
                    "first_frame_image": _data_uri(Path(keyframe)),
                    "duration": int(shot_duration),
                    "resolution": shot_resolution,
                    "ratio": "9:16",
                    "output_path": str(target),
                    "aigc_watermark": False,
                    "timeout_seconds": 900,
                    "poll_interval_seconds": 5,
                }
            )
            if getattr(result, "success", False) and target.is_file():
                record.update({"mode": "video", "clip": str(target), "status": "ok", "prompt": prompt})
            else:
                record.update(
                    {
                        "mode": "still",
                        "image": keyframe,
                        "status": f"video_failed: {str(getattr(result, 'error', ''))[:160]}",
                        "prompt": prompt,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - one shot failing must not stop the film
            record.update({"mode": "still", "image": keyframe, "status": f"error: {type(exc).__name__}: {exc}"[:160], "prompt": prompt})
        shots[beat_id] = record

    doc = {"version": 1, "mode": mode, "model": model, "shots": shots}
    (out / "shots.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def _shot_prompt(beat: dict[str, Any], script_beat: dict[str, Any] | None) -> str:
    visual = beat.get("visual") or {}
    action = str((script_beat or {}).get("shot") or visual.get("action") or "人物自然交谈")
    return (
        f"从首帧开始的一个连续镜头：{action}。"
        "人物、服装、场景与首帧保持一致；镜头稳定，轻微手持；"
        "不要出现文字、字幕、水印；不要切镜，不要淡入淡出。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adplus.recreate.render_cli")
    parser.add_argument("skeleton")
    parser.add_argument("--board", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--script")
    parser.add_argument("--mode", choices=["video", "still"], default="video")
    parser.add_argument("--provider", choices=["minimax", "seedance"], default="minimax")
    parser.add_argument("--reference", help="Seedance reference image (stylized; Ark rejects photoreal faces)")
    parser.add_argument("--model", default="MiniMax-H3")
    parser.add_argument("--resolution", help="H3: 2K; Hailuo: 768P/1080P")
    parser.add_argument("--seconds", type=int, help="clip length requested from the provider")
    find = parser.parse_args(argv)

    skeleton = json.loads(Path(find.skeleton).read_text(encoding="utf-8"))
    board = json.loads(Path(find.board).read_text(encoding="utf-8"))
    script = json.loads(Path(find.script).read_text(encoding="utf-8")) if find.script else None
    if find.provider == "seedance" and find.mode != "still":
        from adplus.recreate import render_seedance

        doc = render_seedance.render_seedance(skeleton, script, find.out, reference=find.reference, model_variant="standard")
    else:
        doc = render(
            skeleton, board, script, find.out,
            mode=find.mode, model=find.model,
            resolution=find.resolution, seconds=find.seconds,
        )
    for beat_id, record in doc["shots"].items():
        print(f"  {beat_id:>3} {record['mode']:<6} {record['status']:<40} {record.get('clip') or record.get('image')}")
    print(f"\nshots: {Path(find.out) / 'shots.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
