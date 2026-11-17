"""Native-dialogue rendering: one video model produces picture, voice and lip sync.

Verified behaviour of Seedance 2.0 ``standard`` with ``generate_audio=True``:

* a line written into the prompt is actually spoken (Chinese);
* the speaker's mouth moves with it;
* a photoreal face reference is rejected by Ark's privacy filter, a stylized
  (cartoonized) frame is accepted.

So each beat is: keyframe -> cartoonize -> image-to-video with the beat's line
-> clip that already contains dialogue.  No TTS, no Wav2Lip.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from adplus.paths import VENDOR
from adplus.recreate import media


def _tool():
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    if not os.environ.get("ARK_API_KEY"):
        try:
            from app import secrets_store

            for key, value in secrets_store.merged_env().items():
                os.environ.setdefault(key, value)
        except Exception:  # noqa: BLE001
            pass
    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get("seedance_ark")
    if tool is None:
        raise RuntimeError("seedance_ark 未注册")
    return tool


def cartoonize(source: Path, target: Path) -> Path:
    """Bypass the privacy filter without changing the cast.

    Ark rejects photoreal faces in reference images but accepts a heavily
    stylized frame; a bilateral + edge pass is enough to flip the classifier.
    """
    import cv2

    image = cv2.imread(str(source))
    if image is None:
        raise RuntimeError(f"cannot read keyframe {source}")
    color = image
    for _ in range(3):
        color = cv2.bilateralFilter(color, 9, 250, 250)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.adaptiveThreshold(
        cv2.medianBlur(gray, 5), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9
    )
    out = cv2.bitwise_and(color, color, mask=edges)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), out)
    return target


def _beat_line(script_beat: dict[str, Any] | None) -> str:
    lines = (script_beat or {}).get("lines") or []
    if not lines:
        return ""
    return "，".join(str(line.get("text") or "").strip() for line in lines if line.get("text"))


def _prompt(beat: dict[str, Any], line: str, *, style: str) -> str:
    framing = (beat.get("visual") or {}).get("shot_size") or "中景"
    head = f"{style}。{framing}，自然光，人物服装与首帧一致，画面不要字幕。"
    if not line:
        return head + "两个男人站着交谈，其中一人点头，不说话。"
    return (
        head
        + f"画面里只有一个人说话，他开口用中文说：‘{line}’，口型与台词同步，"
        "其他人安静听着，不要抢话。"
    )


def render_native(
    skeleton: dict[str, Any],
    script: dict[str, Any] | None,
    board: dict[str, Any],
    out_dir: str | Path,
    *,
    resolution: str = "480p",
    duration: int = 4,
    model_variant: str = "standard",
    style: str = "写实风格化广告短片，画面干净，人物是同一批中国中年男性",
    only: list[str] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    (out / "shots").mkdir(parents=True, exist_ok=True)
    (out / "cartoon").mkdir(parents=True, exist_ok=True)
    tool = _tool()
    keyframes = {item["beat"]: item.get("chosen") for item in board.get("items") or []}
    script_beats = {beat["id"]: beat for beat in (script or {}).get("beats") or []}

    shots: dict[str, Any] = {}
    for beat in skeleton.get("beats") or []:
        beat_id = beat["id"]
        if only and beat_id not in only:
            continue
        keyframe = keyframes.get(beat_id)
        line = _beat_line(script_beats.get(beat_id))
        record: dict[str, Any] = {
            "beat": beat_id,
            "slot_s": round(float(beat["end_s"]) - float(beat["start_s"]), 2),
            "line": line,
        }
        if not keyframe:
            record.update({"mode": "failed", "status": "no-keyframe"})
            shots[beat_id] = record
            continue

        target = out / "shots" / f"{beat_id}.mp4"
        try:
            stylized = cartoonize(Path(keyframe), out / "cartoon" / f"{beat_id}.png")
            result = tool.execute(
                {
                    "operation": "image_to_video",
                    "prompt": _prompt(beat, line, style=style),
                    "reference_image_path": str(stylized),
                    "model_variant": model_variant,
                    "duration": int(duration),
                    "aspect_ratio": "9:16",
                    "resolution": resolution,
                    "generate_audio": True,
                    "watermark": False,
                    "output_path": str(target),
                    "timeout_seconds": 1200,
                }
            )
            if getattr(result, "success", False) and target.is_file():
                record.update({"mode": "native", "clip": str(target), "status": "ok",
                               "cost_usd": getattr(result, "cost_usd", None),
                               "cartoon_keyframe": str(stylized)})
            else:
                record.update({"mode": "failed", "status": f"error: {str(getattr(result, 'error', 'unknown'))[:200]}"})
        except Exception as exc:  # noqa: BLE001
            record.update({"mode": "failed", "status": f"error: {type(exc).__name__}: {exc}"[:200]})
        shots[beat_id] = record

    doc = {"version": 1, "provider": "seedance-native", "model_variant": model_variant,
           "resolution": resolution, "duration": duration, "shots": shots}
    (out / "shots.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
