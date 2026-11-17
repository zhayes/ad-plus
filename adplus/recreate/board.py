"""Storyboard: one keyframe per beat, one consistent cast, one product lock.

Two decisions matter here:

* **A cast sheet first.** Character consistency across beats is not achieved by
  repeating "same four men" in the prompt; it is achieved by generating one
  cast reference and passing it as ``subject_reference`` to every keyframe.
* **The label stays blank.** Chinese text inside generated images is reliably
  garbage, so prompts ask for an empty red label block; the real label is
  pasted in the assembly stage.

Frames are 9:16 and 720x1280 — enough for image-to-video, cheap enough to
regenerate one beat without thinking about it.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

from adplus.paths import VENDOR

PRODUCT_WORDS = ("原味瓜子", "瓜子袋", "瓜子", "泡脚桶")
STYLE = (
    "竖屏 9:16 广告剧照，中国南方城市小区林荫道，白天自然光，浅景深，"
    "写实风格化（接近真人的 3D 渲染质感，不要明星脸）"
)
NEGATIVE = "画面里不要出现任何文字、标题、片名、字幕、水印、logo（顶部和底部都不要）；标签留白"


def _ensure_env() -> None:
    """Make the vendor tool registry importable and the API key visible."""
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    if not os.environ.get("MINIMAX_API_KEY"):
        try:
            from app import secrets_store

            for key, value in secrets_store.merged_env().items():
                os.environ.setdefault(key, value)
        except Exception:  # noqa: BLE001 - CLI use outside the app shell
            pass


def _reference_uri(path: str | Path) -> str:
    target = Path(path)
    mime = mimetypes.guess_type(target.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(target.read_bytes()).decode('ascii')}"


def _image_tool():
    _ensure_env()
    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get("minimax_image")
    if tool is None:
        raise RuntimeError("minimax_image 未注册")
    return tool


def _generate(tool, prompt: str, target: Path, *, count: int = 1, reference: str | None = None) -> list[Path]:
    """Generate ``count`` candidates into ``target``'s folder; return file paths."""
    target.parent.mkdir(parents=True, exist_ok=True)
    inputs: dict[str, Any] = {
        "prompt": prompt[:1500],
        "model": "image-01",
        "n": max(1, min(4, count)),
        "aspect_ratio": "9:16",
        "response_format": "url",
        "output_path": str(target),
    }
    if reference:
        inputs["subject_reference"] = [{"type": "character", "image_file": _reference_uri(reference)}]

    # The CN key is rejected by the global host (2049 invalid api key); retry
    # the other region once instead of failing the whole board.
    previous = os.environ.get("MINIMAX_REGION")
    configured = previous or "cn"
    attempts = [configured] + [region for region in ("cn", "global") if region != configured]
    result, errors = None, []
    try:
        for region in attempts:
            os.environ["MINIMAX_REGION"] = region
            result = tool.execute(inputs)
            if getattr(result, "success", False):
                break
            message = str(getattr(result, "error", "image generation failed"))
            errors.append(f"{region}: {message}")
            if "2049" not in message and "invalid api key" not in message.lower():
                break
    finally:
        if previous is None:
            os.environ.pop("MINIMAX_REGION", None)
        else:
            os.environ["MINIMAX_REGION"] = previous
    if result is None or not getattr(result, "success", False):
        raise RuntimeError("image generation failed: " + " | ".join(errors))

    outputs = [Path(value) for value in ((getattr(result, "data", {}) or {}).get("outputs") or [])]
    paths = [path for path in outputs if path.is_file()]
    if not paths:
        raise RuntimeError("image generation returned no files")
    return paths


GENDER_WORDS = {"male": "男性", "female": "女性", "mixed": "两男两女"}
AGE_WORDS = {"young": "25–32 岁", "middle": "38–48 岁", "senior": "55–65 岁"}
BUILD_WORDS = {"slim": "偏瘦", "normal": "标准体型", "sturdy": "偏壮"}


def cast_description(spec: dict[str, Any] | None) -> str:
    """Turn gender/age/build settings into one prompt sentence."""
    spec = spec or {}
    gender = GENDER_WORDS.get(str(spec.get("gender") or "male"), "男性")
    age = AGE_WORDS.get(str(spec.get("age") or "middle"), "38–48 岁")
    build = BUILD_WORDS.get(str(spec.get("build") or "normal"), "标准体型")
    count = int(spec.get("count") or 4)
    return (
        f"{count}名中国{gender}，{age}，{build}，"
        "短发干净、穿着日常衬衫或 Polo，表情自然、不要明星脸"
    )


def build_cast(product: dict[str, Any], out_dir: str | Path, *, count: int = 2) -> dict[str, Any]:
    """Generate the four-person cast sheet used as the character reference."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spec = product.get("cast_spec") or {}
    descriptions = spec.get("description") or cast_description(spec)
    prompt = (
        f"{STYLE}。人物设定：{descriptions}。站成一排的正面全身合影，背景是小区林荫道。"
        f"手里各提一袋透明自立袋零食。{NEGATIVE}"
    )
    tool = _image_tool()
    paths = _generate(tool, prompt, out / "cast" / "cast.png", count=count)
    return {"prompt": prompt, "candidates": [str(p) for p in paths], "chosen": str(paths[0])}


def _beat_prompt(beat: dict[str, Any], script_beat: dict[str, Any] | None, product: dict[str, Any]) -> str:
    visual = beat.get("visual") or {}
    action = _clean_action(str(visual.get("action") or ""))
    framing = str(visual.get("shot_size") or "中景")
    camera = str(visual.get("camera") or "固定")
    line = " ".join(item.get("text", "") for item in (script_beat or {}).get("lines") or [])
    shot = str((script_beat or {}).get("shot") or "")
    name = str(product.get("name") or "商品")

    parts = [
        STYLE,
        f"人物与服装：与参考图完全一致的四名中国中年男性（同发型、同服装）",
        f"画面：{action or shot or '四人站着交谈'}",
        f"景别：{framing}；机位：{camera}",
        f"商品：一人手持一袋透明自立袋装的{name}，袋上红色竖标签留白（不写字）",
        NEGATIVE,
    ]
    if line:
        parts.append(f"情绪参考（不要写成字幕）：{line}")
    return "。".join(part for part in parts if part)


def _clean_action(text: str) -> str:
    """Strip the reference product from a VLM description, keep the blocking."""
    cleaned = text
    for word in PRODUCT_WORDS:
        cleaned = cleaned.replace(word, "商品")
    cleaned = re.sub(r"[，,]\s*(其中)?一人手里拿着[^，。]*", "", cleaned)
    return cleaned.strip("，。 ")


def build_board(
    skeleton: dict[str, Any],
    script: dict[str, Any] | None,
    product: dict[str, Any],
    out_dir: str | Path,
    *,
    cast_path: str | Path | None = None,
    per_beat: int = 1,
) -> dict[str, Any]:
    """Generate one keyframe per beat. Returns a board document."""
    out = Path(out_dir)
    (out / "board").mkdir(parents=True, exist_ok=True)
    cast = cast_path or (product.get("cast") or {}).get("chosen")
    tool = _image_tool()

    script_beats = {beat["id"]: beat for beat in (script or {}).get("beats") or []}
    items: list[dict[str, Any]] = []
    for beat in skeleton.get("beats") or []:
        prompt = _beat_prompt(beat, script_beats.get(beat["id"]), product)
        try:
            paths = _generate(tool, prompt, out / "board" / f"{beat['id']}.png", count=per_beat, reference=cast)
            items.append(
                {
                    "beat": beat["id"],
                    "start_s": beat["start_s"],
                    "end_s": beat["end_s"],
                    "prompt": prompt,
                    "images": [str(p) for p in paths],
                    "chosen": str(paths[0]),
                    "status": "ok",
                }
            )
        except Exception as exc:  # noqa: BLE001 - one bad beat must not kill the board
            items.append({"beat": beat["id"], "prompt": prompt, "images": [], "chosen": None, "status": f"error: {exc}"[:200]})

    board = {
        "version": 1,
        "cast": str(cast) if cast else None,
        "items": items,
        "cost_estimate_usd": round(len(items) * per_beat * 0.0035, 3),
    }
    (out / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
    return board
