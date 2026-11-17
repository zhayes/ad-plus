"""One-call generation: a single clip that already contains the whole dialogue.

Verified: Seedance 2.0 standard accepts the full script in one prompt, speaks
every line in order with matching mouth movement, and keeps the cast when the
reference is the stylized cast sheet.  That removes the per-beat shots, the TTS
track and Wav2Lip entirely.

Subtitles are timed from the generated audio (ASR), not from the original
beat grid — the model paces itself, so the written script would be out of sync.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from adplus.paths import VENDOR
from adplus.recreate import board as board_mod
from adplus.recreate import media, render_native


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
    return registry.get("seedance_ark")


def script_dialogue(script: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten a script into ordered (speaker, line) pairs."""
    rows: list[tuple[str, str]] = []
    for beat in script.get("beats") or []:
        for line in beat.get("lines") or []:
            text = str(line.get("text") or "").strip()
            if text:
                rows.append((str(line.get("speaker") or "A")[:1], text))
    return rows


def build_prompt(script: dict[str, Any], product: dict[str, Any], *, seconds: int, with_product_image: bool = False) -> str:
    cast = board_mod.cast_description(product.get("cast_spec"))
    rows = script_dialogue(script)
    words = max(1, int(seconds * 4.2))

    def who(speaker: str) -> str:
        return "白衬衫男" if speaker == "A" else "蓝衬衫男"

    if not rows:
        body = "几个人站着聊天，偶尔点头，没有对白。"
    else:
        spoken = "；".join(f"{who(speaker)}说：‘{text}’" for speaker, text in rows)
        body = f"全程中文同期对白，按顺序说完，不要旁白：{spoken}。"

    product_note = ""
    if with_product_image:
        product_note = "图2是商品包装参考：画面里的零食袋外观必须与图2一致（袋型、标签颜色），不要自行发明包装。"
    return (
        f"{cast}，站在中国南方小区林荫道上聊天，其中一人提着{product.get('name') or '零食'}的包装袋。"
        f"{product_note}{body}"
        f"一镜到底，中景为主，自然光，口型与台词同步，画面不要字幕、不要水印。"
        f"全片约 {seconds} 秒，台词总字数控制在 {words} 字以内。"
    )


def render_oneshot(
    skeleton: dict[str, Any],
    script: dict[str, Any],
    product: dict[str, Any],
    out_dir: str | Path,
    *,
    cast: str | Path,
    resolution: str = "480p",
    model_variant: str = "standard",
    max_seconds: int = 15,
    product_image: str | Path | None = None,
    seconds_override: int | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    (out / "oneshot").mkdir(parents=True, exist_ok=True)
    source_s = float((skeleton.get("source") or {}).get("duration_s") or 11.0)
    rows = script_dialogue(script)
    chars = sum(len(text) for _, text in rows)
    # ~4.2 chars/s of natural speech plus a little air at both ends.
    seconds = int(seconds_override or max(4, min(max_seconds, math.ceil(max(source_s, chars / 4.2 + 1.2)))))
    prompt = build_prompt(script, product, seconds=seconds, with_product_image=bool(product_image))

    stylized = render_native.cartoonize(Path(cast), out / "oneshot" / "cast_cartoon.png")
    target = out / "oneshot" / "film.mp4"
    tool = _tool()
    # With a real packshot we switch to reference_to_video so the bag in the
    # film can inherit the actual packaging instead of a plausible invention.
    operation = "reference_to_video" if product_image else "image_to_video"
    inputs: dict[str, Any] = {
        "operation": operation,
        "prompt": prompt,
        "model_variant": model_variant,
        "duration": seconds,
        "aspect_ratio": "9:16",
        "resolution": resolution,
        "generate_audio": True,
        "watermark": False,
        "output_path": str(target),
        "timeout_seconds": 1800,
    }
    if product_image:
        inputs["reference_image_paths"] = [str(stylized), str(product_image)]
    else:
        inputs["reference_image_path"] = str(stylized)
    result = tool.execute(inputs)
    if not getattr(result, "success", False) or not target.is_file():
        raise RuntimeError(f"oneshot failed: {str(getattr(result, 'error', 'unknown'))[:240]}")

    doc = {
        "version": 1,
        "provider": "seedance-oneshot",
        "prompt": prompt,
        "requested_seconds": seconds,
        "clip": str(target),
        "duration_s": round(media.probe(target)["duration_s"], 2),
        "cost_usd": getattr(result, "cost_usd", None),
        "script": [{"speaker": speaker, "text": text} for speaker, text in rows],
    }
    (out / "oneshot" / "film.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
