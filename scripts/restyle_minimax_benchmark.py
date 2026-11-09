"""MiniMax-only Restyle benchmark.

MiniMax is the configured provider for Restyle tests.  The video tool requires
public URLs (or ``mm_file://<id>``); this script uploads local reference media
with MiniMax's file API (purpose=video_generation_input) and then calls the
existing ``minimax_video`` tool.  No other provider is touched.

Examples:
    python scripts/restyle_minimax_benchmark.py --check
    python scripts/restyle_minimax_benchmark.py --upload-check
    python scripts/restyle_minimax_benchmark.py \
      --video /path/shot.mp4 --reference /path/outfit.png \
      --prompt "..." --duration 4 --output /tmp/outfit.mp4
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "openmontage"
for path in (str(ROOT), str(VENDOR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app import secrets_store  # noqa: E402
from tools.tool_registry import registry  # noqa: E402

os.environ.update(secrets_store.merged_env())

BASE_URLS = {
    "global": "https://api.minimax.io",
    "global_en": "https://api.minimax.io",
    "cn": "https://api.minimaxi.com",
    "cn_zh": "https://api.minimaxi.com",
}


def _base_url() -> str:
    region = os.environ.get("MINIMAX_REGION", "global").strip().lower()
    return BASE_URLS.get(region, BASE_URLS["global"])


def _key() -> str | None:
    return os.environ.get("MINIMAX_API_KEY")


def upload(path: Path) -> str:
    import requests

    key = _key()
    if not key:
        raise RuntimeError("MINIMAX_API_KEY is not configured")
    with path.open("rb") as handle:
        response = requests.post(
            f"{_base_url()}/v1/files/upload",
            headers={"Authorization": f"Bearer {key}"},
            data={"purpose": "video_generation_input"},
            files={"file": (path.name, handle, _mime(path))},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    status = (payload.get("base_resp") or {}).get("status_code")
    if status not in (0, None):
        raise RuntimeError(f"MiniMax upload failed: {payload.get('base_resp')}")
    file_id = (payload.get("file") or {}).get("file_id")
    if not file_id:
        raise RuntimeError(f"MiniMax upload returned no file_id: {payload}")
    return f"mm_file://{file_id}"


def _mime(path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.environ.get("MINIMAX_REGION", "global"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--upload-check", action="store_true")
    parser.add_argument("--video")
    parser.add_argument("--reference")
    parser.add_argument("--prompt", default="Change only the outfit to the reference clothing. Keep product, hands, face, background, camera movement and timing unchanged.")
    parser.add_argument("--duration", type=int, default=4)
    parser.add_argument("--output", default="/tmp/restyle_minimax.mp4")
    parser.add_argument("--model", default="MiniMax-H3")
    args = parser.parse_args()

    os.environ["MINIMAX_REGION"] = args.region
    registry.ensure_discovered()
    tool = registry.get("minimax_video")
    if tool is None:
        print("minimax_video is not registered", file=sys.stderr)
        return 2
    print(f"minimax_video: {getattr(tool.get_status(), 'value', tool.get_status())}")
    print(f"base_url: {_base_url()}")
    print(f"key configured: {bool(_key())}")
    if args.check:
        return 0 if getattr(tool.get_status(), "value", "") == "available" else 2

    if args.upload_check:
        # Synthetic upload: do not send a real person just to test plumbing.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "color.png"
            Image.fromarray(np.full((512, 512, 3), (40, 120, 160), dtype=np.uint8)).save(path)
            try:
                url = upload(path)
                print(f"upload OK: {url}")
                return 0
            except Exception as exc:  # noqa: BLE001
                print(f"upload FAILED: {exc}", file=sys.stderr)
                return 1

    if not args.video:
        print("--video is required for a generation run", file=sys.stderr)
        return 2
    video = Path(args.video)
    if not video.is_file():
        print(f"video not found: {video}", file=sys.stderr)
        return 2
    if getattr(tool.get_status(), "value", "") != "available":
        print("MiniMax is not available (check MINIMAX_API_KEY)", file=sys.stderr)
        return 2

    try:
        print("uploading reference video...")
        video_ref = upload(video)
        reference_ref = upload(Path(args.reference)) if args.reference else None
    except Exception as exc:  # noqa: BLE001
        print(f"upload FAILED: {exc}", file=sys.stderr)
        return 1

    inputs = {
        "operation": "reference_to_video",
        "model": args.model,
        "prompt": args.prompt,
        "reference_video_url": video_ref,
        "duration": args.duration,
        "ratio": "9:16",
        "output_path": str(Path(args.output).resolve()),
        "prompt_optimizer": True,
    }
    if reference_ref:
        inputs["reference_image_urls"] = [reference_ref]
    print("submitting MiniMax reference_to_video...")
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
