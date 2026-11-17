"""Shot rendering through Ark Seedance (Doubao).

Seedance is the fallback when MiniMax has no balance: it runs a text-to-video
or reference-to-video task and polls until the clip is ready.  Two constraints
shape this module:

* the reference image is optional — Ark rejects photorealistic face references
  with ``InputImageSensitiveContentDetected``, so the caller passes a stylized
  sheet (or none);
* a 4s clip is the minimum and is trimmed into the beat slot later, so a
  1.4s beat still costs a 4s generation.  Cheaper than a failed film.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from adplus.paths import VENDOR


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


SHOT_ACTION = {
    "hook": "四个人并排朝镜头走来，步伐一致，其中一人手提一袋零食",
    "setup": "两人面对面站定交谈，其中一人手里提着零食袋，自然点头",
    "escalation": "其中一人把零食袋举起来给对方看，手部动作清晰",
    "insult": "一人正脸近景，面无表情地说了一句话，对方表情一僵",
    "cta": "一人把袋子往怀里收了一下，另一人凑近听",
    "punchline": "一人抱住袋子转身向画面外跑去，其余人愣在原地",
    "beat": "四个人站着交谈，轻微移动",
}


def _prompt(beat: dict[str, Any], script_beat: dict[str, Any] | None, *, style: str) -> str:
    action = (script_beat or {}).get("shot") or SHOT_ACTION.get(str(beat.get("function")), "人物自然交谈")
    line = "，".join(item.get("text", "") for item in (script_beat or {}).get("lines") or [])
    parts = [
        style,
        f"画面：{action}",
        "人物：四名中国中年男性，白衬衫、浅蓝衬衫、深灰 Polo、米色衬衫，短寸头，表情自然",
        "场景：中国南方小区林荫道，白天自然光，浅景深",
        "镜头：中景，轻微手持，一镜到底，不要切镜",
        "不要出现文字、字幕、水印、logo",
    ]
    if line:
        parts.append(f"情绪参考（不要念出来）：{line}")
    return "。".join(parts)


def render_seedance(
    skeleton: dict[str, Any],
    script: dict[str, Any] | None,
    out_dir: str | Path,
    *,
    reference: str | Path | None = None,
    model_variant: str = "standard",
    duration: int = 4,
    resolution: str = "720p",
    style: str = "写实风格化广告短片，接近真人的渲染质感，不要明星脸",
    retries: int = 1,
    only: list[str] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    (out / "shots").mkdir(parents=True, exist_ok=True)
    tool = _tool()
    script_beats = {beat["id"]: beat for beat in (script or {}).get("beats") or []}
    shots: dict[str, Any] = {}

    for beat in skeleton.get("beats") or []:
        beat_id = beat["id"]
        if only and beat_id not in only:
            continue
        target = out / "shots" / f"{beat_id}.mp4"
        prompt = _prompt(beat, script_beats.get(beat_id), style=style)
        record: dict[str, Any] = {"beat": beat_id, "slot_s": round(float(beat["end_s"]) - float(beat["start_s"]), 2), "prompt": prompt}
        last_error = ""
        for attempt in range(retries + 1):
            try:
                inputs: dict[str, Any] = {
                    "operation": "reference_to_video" if reference else "text_to_video",
                    "prompt": prompt,
                    "model_variant": model_variant,
                    "duration": max(4, min(15, int(duration))),
                    "aspect_ratio": "9:16",
                    "resolution": resolution,
                    "generate_audio": False,
                    "watermark": False,
                    "output_path": str(target),
                    "timeout_seconds": 1200,
                }
                if reference:
                    inputs["reference_image_path"] = str(reference)
                result = tool.execute(inputs)
                if getattr(result, "success", False) and target.is_file():
                    record.update({"mode": "video", "clip": str(target), "status": "ok", "cost_usd": getattr(result, "cost_usd", None)})
                    break
                last_error = str(getattr(result, "error", "unknown"))[:240]
                # A privacy rejection is deterministic; retrying only burns time.
                if "SensitiveContent" in last_error or "Privacy" in last_error:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"[:240]
            time.sleep(2)
        else:
            record.update({"mode": "failed", "status": f"error: {last_error}"})
        if "clip" not in record:
            record.update({"mode": "failed", "status": f"error: {last_error}"})
        shots[beat_id] = record

    doc = {"version": 1, "provider": "seedance", "model_variant": model_variant, "reference": str(reference) if reference else None, "shots": shots}
    (out / "shots.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
