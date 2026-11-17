"""Generate a silent base-performance video for a persona.

Wav2Lip only replaces the mouth region.  A still portrait therefore produces
"photo with moving lips", not a performance.  This helper creates a short
image-to-video base with Seedance so the persona has real head/body motion.
It is explicit and paid: never call it implicitly from a batch job.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from adplus import personas
from adplus.paths import PERSONAS, WORKSPACE


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE.resolve()))
    except (ValueError, OSError):
        return str(path)


def generate(
    persona_id: str,
    *,
    prompt: str = "",
    duration: int = 5,
    resolution: str = "480p",
    provider: str = "seedance",
) -> dict[str, Any]:
    persona = personas.load_persona(persona_id)
    if persona is None:
        raise FileNotFoundError(persona_id)
    source = str(persona.get("source_path") or "")
    source_path = Path(source) if Path(source).is_absolute() else WORKSPACE / source
    if not source_path.is_file():
        raise ValueError("persona 没有可用的人像主图")
    try:
        from app.capabilities import apply_secrets_to_env
        apply_secrets_to_env()
    except Exception:
        pass
    from tools.tool_registry import registry

    registry.discover()
    tool_name = "seedance_ark" if provider == "seedance" else "minimax_video"
    tool = registry.get(tool_name)
    if tool is None:
        raise RuntimeError(f"{tool_name} is not registered")
    out_dir = PERSONAS / persona_id
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"base_{int(time.time())}.mp4"
    text = prompt.strip() or (
        "Young Chinese woman talking to camera, natural upper-body movement, "
        "subtle hand gestures, relaxed shoulders, clean studio background, "
        "static medium shot, realistic, no text, no captions"
    )
    if provider == "minimax":
        data_uri = "data:image/png;base64," + base64.b64encode(source_path.read_bytes()).decode("ascii")
        requested = max(4, min(10, int(duration)))
        minimax_duration = 6 if requested <= 6 else 10
        inputs = {
            "operation": "image_to_video",
            "model": "MiniMax-Hailuo-2.3-Fast",
            "first_frame_image": data_uri,
            "prompt": text,
            "duration": minimax_duration,
            "resolution": "768P",
            "aspect_ratio": "9:16",
            "output_path": str(output),
        }
        previous_region = os.environ.get("MINIMAX_REGION")
        result = None
        last_error = ""
        for region in ("cn", "global"):
            try:
                os.environ["MINIMAX_REGION"] = region
                candidate = tool.execute(inputs)
                if getattr(candidate, "success", False):
                    result = candidate
                    break
                error = str(getattr(candidate, "error", ""))
                last_error = error
                result = candidate
                if region == "cn" and "2049" not in error and "invalid api key" not in error.lower():
                    break
            except Exception as exc:
                last_error = str(exc)
                result = None
                break
        if previous_region is None:
            os.environ.pop("MINIMAX_REGION", None)
        else:
            os.environ["MINIMAX_REGION"] = previous_region
        if result is None:
            raise ValueError(last_error or "MiniMax 形象视频生成失败")
    else:
        result = tool.execute({
            "task_action": "generate",
            "operation": "image_to_video",
            "model_variant": "standard",
            "reference_image_path": str(source_path),
            "prompt": text,
            "duration": max(4, min(10, int(duration))),
            "resolution": resolution,
            "aspect_ratio": "9:16",
            "generate_audio": False,
            "output_path": str(output),
        })
    if not getattr(result, "success", False):
        error = str(getattr(result, "error", "基础视频生成失败"))
        lowered = error.lower()
        if "real person" in lowered or "privacyinformation" in lowered or "sensitivecontent" in lowered:
            raise ValueError(
                "Seedance 拒绝真实人物图片（隐私合规限制），不能用这张模特图生成形象视频。"
                "请上传本人基础表演视频，或改用 MiniMax / Kling / HeyGen。"
            )
        raise ValueError(error)
    row = {
        "id": f"base_{int(time.time())}",
        "path": _rel(output),
        "framing": "half_body",
        "duration_s": max(4, min(10, int(duration))),
        "silent": True,
        "source": provider,
    }
    persona["base_videos"] = [*(persona.get("base_videos") or []), row]
    personas.save_persona(persona, persona_id)
    return {"persona": persona, "base_video": row, "cost_usd": float(getattr(result, "cost_usd", 0) or 0)}
