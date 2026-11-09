"""M0b: benchmark an existing video_edit provider on one Restyle shot.

Uses the Atlas Cloud video_edit route already registered in OpenMontage
(``atlas_video``).  No new SDK, no second orchestrator.

Example:
    python scripts/restyle_edit_benchmark.py --check
    python scripts/restyle_edit_benchmark.py \
      --video projects/p/source.mp4 \
      --reference assets/outfit.png \
      --prompt "Change only the outfit to a black knit set; keep product, hands, face, background, camera and timing unchanged." \
      --output /tmp/outfit_edit.mp4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "openmontage"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from tools.tool_registry import registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", help="source video/shot path")
    parser.add_argument("--reference", help="target outfit reference image")
    parser.add_argument("--prompt", default="Change only the outfit. Keep product, hands, face, background, camera and timing unchanged.")
    parser.add_argument("--output", default="/tmp/restyle_edit.mp4")
    parser.add_argument("--model", default="google/gemini-omni-flash/video-edit")
    parser.add_argument("--check", action="store_true", help="only inspect availability/model, do not call")
    args = parser.parse_args()

    registry.ensure_discovered()
    tool = registry.get("atlas_video")
    if tool is None:
        print("atlas_video is not registered", file=sys.stderr)
        return 2
    status = tool.get_status()
    info = tool.get_info()
    print(f"atlas_video: {getattr(status, 'value', status)}")
    catalog = info.get("model_catalog") or {}
    edit_models = {k: v for k, v in catalog.items() if v.get("operation") == "video_edit"}
    print("video_edit models:")
    for model, spec in sorted(edit_models.items()):
        print(f"  {model}  {spec.get('resolutions')}  ${spec.get('cost_per_second')}/s")

    if args.check:
        if getattr(status, "value", status) != "available":
            print("\nBLOCKED: set ATLASCLOUD_API_KEY (or ATLAS_CLOUD_API_KEY) to run the benchmark.")
            return 2
        return 0

    if not args.video:
        print("--video is required for a real run", file=sys.stderr)
        return 2
    if not Path(args.video).is_file():
        print(f"video not found: {args.video}", file=sys.stderr)
        return 2
    if getattr(status, "value", status) != "available":
        print("\nBLOCKED: set ATLASCLOUD_API_KEY (or ATLAS_CLOUD_API_KEY) to run the benchmark.", file=sys.stderr)
        return 2

    inputs = {
        "operation": "video_edit",
        "model": args.model,
        "prompt": args.prompt,
        "video_path": str(Path(args.video).resolve()),
        "output_path": str(Path(args.output).resolve()),
    }
    if args.reference:
        inputs["reference_images"] = [str(Path(args.reference).resolve())]

    result = tool.execute(inputs)
    print(json.dumps(
        {
            "success": result.success,
            "error": result.error,
            "data": result.data,
            "artifacts": result.artifacts,
            "duration_seconds": result.duration_seconds,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
