"""Auto-generate fictional digital-presenter portraits.

This is an Ad+ domain adapter over the upstream MiniMax image tool.  It does
not call a provider directly: the ToolRegistry owns execution, pricing, region
and error handling.  The generated files are only candidates; the user still
chooses one and creates the persona record explicitly.
"""

from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from adplus.paths import UPLOADS

DEFAULT_PROMPT = (
    "professional Chinese ecommerce presenter, fictional person, natural skin texture, "
    "clean studio portrait, soft key light, looking at camera, calm confident expression, "
    "minimal makeup, no celebrity likeness, no logos, editorial photography, 85mm lens"
)


def _reference_uri(path: str | Path) -> str:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    mime = mimetypes.guess_type(target.name)[0] or "image/png"
    encoded = base64.b64encode(target.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def generate_candidates(
    *,
    prompt: str,
    count: int = 4,
    aspect_ratio: str = "3:4",
    reference_path: str | Path | None = None,
    model: str = "image-01",
) -> dict[str, Any]:
    from tools.tool_registry import registry

    registry.discover()
    tool = registry.get("minimax_image")
    if tool is None:
        raise RuntimeError("minimax_image tool is not registered")
    status = tool.get_status()
    if str(getattr(status, "value", status)) != "available":
        raise RuntimeError("minimax_image is unavailable; set MINIMAX_API_KEY")

    out_dir = UPLOADS / "personas" / uuid.uuid4().hex[:10]
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs: dict[str, Any] = {
        "prompt": (prompt or DEFAULT_PROMPT)[:1500],
        "model": model,
        "n": max(1, min(4, int(count))),
        "aspect_ratio": aspect_ratio,
        "response_format": "url",
        "output_path": str(out_dir / "candidate.png"),
    }
    if reference_path:
        inputs["subject_reference"] = [{"type": "character", "image_file": _reference_uri(reference_path)}]

    import os

    previous = os.environ.get("MINIMAX_REGION")
    configured = previous or "global"
    attempts = [configured] + [region for region in ("cn", "global") if region != configured]
    result = None
    errors: list[str] = []
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
    outputs = list((getattr(result, "data", {}) or {}).get("outputs") or [])
    if not outputs:
        raise RuntimeError("image generation returned no files")
    candidates = []
    for index, value in enumerate(outputs, 1):
        path = Path(value)
        if not path.is_file():
            continue
        candidates.append({
            "index": index,
            "path": str(path.resolve().relative_to(UPLOADS.parent.resolve())),
            "filename": path.name,
        })
    if not candidates:
        raise RuntimeError("generated files were not written")
    return {
        "candidates": candidates,
        "prompt": inputs["prompt"],
        "model": model,
        "aspect_ratio": aspect_ratio,
        "reference_used": bool(reference_path),
        "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
    }
