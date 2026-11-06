"""Ad+ extensions registered into the OpenMontage ToolRegistry.

Only domain-specific deterministic tools live here.  Generation providers stay
upstream; this module must not become a second provider layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adplus import product_composite
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


class ProductPlateTool(BaseTool):
    """Overlay a locked real product image onto an existing video."""

    name = "product_plate"
    version = "1.0.0"
    tier = ToolTier.ENHANCE
    capability = "video_generation"
    provider = "adplus"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg"]
    install_instructions = "Install ffmpeg; no API key is required."

    capabilities = ["product_plate", "overlay", "label_preservation"]
    supports = {"offline": True, "real_product": True, "native_audio": False}
    best_for = ["commerce ads where the real SKU must not be regenerated"]
    not_good_for = ["replacing the product with a generated garment"]
    input_schema = {
        "type": "object",
        "required": ["base_video_path", "product_image_path", "output_path"],
        "properties": {
            "base_video_path": {"type": "string"},
            "product_image_path": {"type": "string"},
            "output_path": {"type": "string"},
            "start_s": {"type": "number", "default": 2.0},
            "end_s": {"type": "number", "default": 8.0},
            "position": {"type": "string", "enum": ["bottom_left", "bottom_right", "top_left", "top_right"], "default": "bottom_right"},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=200, network_required=False)
    side_effects = ["writes a product-plate composite to output_path"]
    user_visible_verification = ["Watch that the real product and label remain readable"]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 15.0

    def get_status(self):  # noqa: ANN201 - upstream enum
        from tools.base_tool import ToolStatus
        import shutil

        return ToolStatus.AVAILABLE if shutil.which("ffmpeg") else ToolStatus.UNAVAILABLE

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            result = product_composite.composite_files(
                inputs["base_video_path"], inputs["product_image_path"], inputs["output_path"],
                start_s=float(inputs.get("start_s", 2.0)),
                end_s=float(inputs.get("end_s", 8.0)),
                position=str(inputs.get("position", "bottom_right")),
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(
            success=bool(result.get("success")),
            data=result,
            artifacts=[str(result["output"])] if result.get("output") else [],
            error=result.get("error"),
            cost_usd=0.0,
            model="ffmpeg-product-plate",
        )


def register() -> list[str]:
    from tools.tool_registry import registry

    registry.register(ProductPlateTool())
    return [ProductPlateTool.name]
