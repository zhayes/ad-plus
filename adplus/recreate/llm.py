"""Text-only LLM helper that always returns parsed JSON.

Kept separate from :mod:`adplus.recreate.vision` because that module carries
image encoding and per-frame caching; this one is for the analysis/adaptation
prompts and is shared by ``gag`` and ``script``.

Failure policy: raise :class:`LLMError`.  Callers decide whether to degrade to
a heuristic result — analysis of a video must never crash because a provider
hiccuped.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

ENDPOINT = os.environ.get("ADPLUS_LLM_ENDPOINT", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("ADPLUS_LLM_MODEL", "deepseek-chat")
TIMEOUT = float(os.environ.get("ADPLUS_LLM_TIMEOUT", "120"))


class LLMError(RuntimeError):
    """The provider did not return usable JSON."""


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    try:
        from app import secrets_store

        return secrets_store.merged_env().get("DEEPSEEK_API_KEY", "")
    except Exception:  # noqa: BLE001 - CLI use outside the app shell
        return ""


def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 2400,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise LLMError("DEEPSEEK_API_KEY 未配置")

    body = {
        "model": model or MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    payload = _post(body, key, timeout or TIMEOUT)
    content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    data = _parse(content)
    if not isinstance(data, dict):
        raise LLMError(f"模型未返回 JSON 对象：{content[:200]}")
    return data


def _post(body: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=timeout)
        if resp.status_code == 400 and "response_format" in resp.text:
            body = {k: v for k, v in body.items() if k != "response_format"}
            resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}"[:240]) from exc


def _parse(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start: end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败：{exc}") from exc
