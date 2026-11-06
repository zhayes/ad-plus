"""Commerce format presets.

A format selects a pipeline and a small set of defaults; it must not become a
second pipeline.  The pipeline name is the source of truth.
"""

from __future__ import annotations

import copy
from typing import Any

FORMATS: list[dict[str, Any]] = [
    {
        "id": "host_product_ad",
        "label": "主播带货",
        "pipeline": "avatar-spokesperson",
        "route": "avatar_spokesperson",
        "duration_s": 10,
        "aspect": "9:16",
        "description": "数字模特口播 + 商品绑定；产品真实性由锁定商品与 plate 保证。",
        "required_capabilities": ["avatar_or_lip_sync", "tts"],
        "best_for": "有明确主播形象和口播卖点的短视频",
    },
    {
        "id": "ugc_testimonial",
        "label": "UGC 口碑",
        "pipeline": "hybrid",
        "route": "hybrid",
        "duration_s": 15,
        "aspect": "9:16",
        "description": "真实素材/自拍为主，生成补镜与字幕。",
        "required_capabilities": ["video_generation", "tts"],
        "best_for": "素人感、真实使用场景",
    },
    {
        "id": "product_demo",
        "label": "商品演示",
        "pipeline": "animation",
        "route": "local_motion",
        "duration_s": 10,
        "aspect": "9:16",
        "description": "商品图、卖点、动效和文字，确定性输出。",
        "required_capabilities": ["motion_graphics"],
        "best_for": "商品细节、参数、价格机制",
    },
]


def list_formats() -> list[dict[str, Any]]:
    return [copy.deepcopy(item) for item in FORMATS]


def get_format(format_id: str) -> dict[str, Any] | None:
    item = next((row for row in FORMATS if row["id"] == format_id), None)
    return copy.deepcopy(item) if item else None
