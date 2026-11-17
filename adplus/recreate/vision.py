"""Frame-level visual tagging through DeepSeek's multimodal endpoint.

Why this provider: the repo already has ``DEEPSEEK_API_KEY``, the endpoint
accepts image parts on the OpenAI-compatible schema, and a single 720x1280
frame costs roughly 200 prompt tokens.  A local CLIP/BLIP2 path exists in the
vendor toolkit but is weak on Chinese scenes and needs a multi-GB download, so
it is not used here.

Every call is cached by image hash + prompt version: re-running an analysis on
the same reference video costs nothing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

PROMPT_VERSION = "v1"
ENDPOINT = os.environ.get("ADPLUS_VLM_ENDPOINT", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("ADPLUS_VLM_MODEL", "deepseek-chat")
MAX_WIDTH = 640
TIMEOUT = 90

SYSTEM = "你是一个广告片场记。只输出 JSON，不要任何解释、不要 markdown 代码块。"

PROMPT = """看这一帧画面，按下面的 JSON 结构填写。不确定的字段填 null，不要编造品牌名或字幕文字。

{
  "shot_size": "特写|近景|中近景|中景|全景 之一",
  "people_count": 整数,
  "people": [{"desc": "一句话描述这个人的外观（性别/年龄感/服装颜色）", "expression": "笑|中性|严肃|惊讶|其他"}],
  "action": "一句话描述画面里正在发生什么动作",
  "setting": "一句话描述场景与环境",
  "product": {"visible": true/false, "what": "画面里的商品是什么（没有则 null）", "prominence": "low|medium|high"},
  "text_in_frame": ["画面里真实可见的文字，没有就空数组"],
  "camera": "固定|轻微手持|跟拍|推|拉|摇|其他",
  "lighting": "自然光|室内光|逆光|夜景|其他",
  "confidence": 0 到 1 的小数
}"""

_CACHE_DIR = Path(os.environ.get("ADPLUS_VLM_CACHE") or (Path.home() / ".cache" / "adplus" / "vlm"))


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    try:
        from app import secrets_store

        return secrets_store.merged_env().get("DEEPSEEK_API_KEY", "")
    except Exception:  # noqa: BLE001 - the pipeline must run outside the app shell too
        return ""


def _encode(path: Path) -> str:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _cache_path(digest: str) -> Path:
    return _CACHE_DIR / f"{digest}-{PROMPT_VERSION}.json"


def tag_frame(path: str | Path, *, context: str = "") -> dict[str, Any]:
    """Return the tag object for one frame. Never raises on model failure."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:24]
    cache = _cache_path(digest)
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    key = _api_key()
    if not key:
        return {"error": "DEEPSEEK_API_KEY missing", "confidence": 0.0}

    text = PROMPT if not context else f"{PROMPT}\n\n这一帧在片中的位置：{context}"
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_encode(path)}"}},
                    {"type": "text", "text": text},
                ],
            },
        ],
        "max_tokens": 500,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=TIMEOUT,
        )
        if resp.status_code == 400 and "response_format" in resp.text:
            body.pop("response_format", None)
            resp = requests.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=TIMEOUT,
            )
        resp.raise_for_status()
        payload = resp.json()
        content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        tag = _parse_json(content)
        tag["_usage"] = payload.get("usage")
    except Exception as exc:  # noqa: BLE001 - a failed tag degrades, never aborts
        return {"error": f"{type(exc).__name__}: {exc}"[:200], "confidence": 0.0}

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(tag, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return tag


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start: end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"raw": data}
    except json.JSONDecodeError:
        return {"raw": text[:400]}


def tag_frames(items: list[tuple[str | Path, str]], *, workers: int = 4) -> list[dict[str, Any]]:
    """Tag several frames concurrently, preserving input order."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
        return list(pool.map(lambda item: tag_frame(item[0], context=item[1]), items))
