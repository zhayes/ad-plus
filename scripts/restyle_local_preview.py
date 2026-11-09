"""Local L1 outfit preview: seed-color garment mask + LAB recolor.

No API key, no model.  This is a controllable first cut for a keyframe:
you point at the garment once, it builds a color mask inside the person mask,
subtracts the product mask, and writes a before/after JPEG.

Example:
    python scripts/restyle_local_preview.py \
      --frame frames/s03.png --person-mask frames/s03_mask.png \
      --product-mask frames/s03_prod.png --seed 300 450 \
      --bbox 100 240 520 700 --color "#2F4F4F" --output /tmp/s03_outfit.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adplus.restyle.outfit import recolor_lab


def load_mask(path: str | None, size: tuple[int, int]) -> np.ndarray:
    if not path:
        return np.full((size[1], size[0]), 255, dtype=np.uint8)
    image = Image.open(path).convert("L").resize(size, Image.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def lab_array(frame: np.ndarray) -> np.ndarray:
    # Use the same manual conversion as outfit.py via a tiny local import.
    from adplus.restyle.outfit import _srgb_to_lab

    return _srgb_to_lab(frame)


def build_garment_mask(
    frame: np.ndarray,
    person: np.ndarray,
    product: np.ndarray,
    seed: tuple[int, int],
    bbox: tuple[int, int, int, int],
    tolerance: float,
) -> np.ndarray:
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = bbox
    x0, x1 = max(0, x0), min(width, x1)
    y0, y1 = max(0, y0), min(height, y1)
    sx, sy = seed
    lab = lab_array(frame)
    seed_lab = lab[sy, sx]
    distance = np.sqrt(((lab - seed_lab) ** 2).sum(axis=-1))
    region = np.zeros((height, width), dtype=np.uint8)
    region[y0:y1, x0:x1] = 255
    mask = ((distance < float(tolerance)) & (person > 127) & (region > 0) & (product < 127))
    return (mask.astype(np.uint8) * 255)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", required=True)
    parser.add_argument("--person-mask")
    parser.add_argument("--product-mask")
    parser.add_argument("--seed", nargs=2, type=int, required=True, metavar=("X", "Y"))
    parser.add_argument("--bbox", nargs=4, type=int, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--tolerance", type=float, default=24.0)
    parser.add_argument("--color", default="#2F4F4F")
    parser.add_argument("--output", default="/tmp/restyle_preview.jpg")
    args = parser.parse_args()

    frame_img = Image.open(args.frame).convert("RGB")
    size = frame_img.size
    frame = np.asarray(frame_img)
    person = load_mask(args.person_mask, size)
    product = load_mask(args.product_mask, size) if args.product_mask else np.zeros((size[1], size[0]), np.uint8)
    garment = build_garment_mask(frame, person, product, tuple(args.seed), tuple(args.bbox), args.tolerance)
    out = recolor_lab(frame, garment, args.color, strength=0.9, feather_radius=2, product_mask=product)

    before = frame_img.copy()
    after = Image.fromarray(out)
    canvas = Image.new("RGB", (size[0] * 2 + 12, size[1]), (16, 20, 28))
    canvas.paste(before, (0, 0))
    canvas.paste(after, (size[0] + 12, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), "before", fill=(255, 255, 255))
    draw.text((size[0] + 24, 12), "after", fill=(255, 255, 255))
    canvas.save(args.output, quality=92)
    print(f"wrote {args.output}  garment={float((garment > 127).mean()):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
