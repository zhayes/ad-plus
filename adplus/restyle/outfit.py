"""Deterministic local outfit compositing primitives (L1).

These functions are deliberately pure: frame + mask + target -> frame.
They do not segment, call a model, or decide which shot to change.  A pipeline
tool/agent supplies the mask; this module only guarantees that:
  * product pixels are excluded before compositing,
  * luminance (folds, shadows, highlights) is preserved,
  * the mask edge is feathered instead of hard-cut.

Keeping this layer deterministic is the quality floor for Restyle.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from PIL import Image, ImageFilter


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"invalid color: {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    linear = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    x = linear[..., 0] * 0.4124564 + linear[..., 1] * 0.3575761 + linear[..., 2] * 0.1804375
    y = linear[..., 0] * 0.2126729 + linear[..., 1] * 0.7151522 + linear[..., 2] * 0.0721750
    z = linear[..., 0] * 0.0193339 + linear[..., 1] * 0.1191920 + linear[..., 2] * 0.9503041
    xyz = np.stack((x / 0.95047, y / 1.0, z / 1.08883), axis=-1)
    delta = 6.0 / 29.0
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4.0 / 29.0)
    return np.stack((
        116.0 * f[..., 1] - 16.0,
        500.0 * (f[..., 0] - f[..., 1]),
        200.0 * (f[..., 1] - f[..., 2]),
    ), axis=-1)


def _lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    lab = np.asarray(lab, dtype=np.float32)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    delta = 6.0 / 29.0
    xyz = np.stack((
        np.where(fx > delta, fx ** 3, 3 * delta ** 2 * (fx - 4.0 / 29.0)) * 0.95047,
        np.where(fy > delta, fy ** 3, 3 * delta ** 2 * (fy - 4.0 / 29.0)) * 1.0,
        np.where(fz > delta, fz ** 3, 3 * delta ** 2 * (fz - 4.0 / 29.0)) * 1.08883,
    ), axis=-1)
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    rgb = np.stack((
        x * 3.2404542 + y * -1.5371385 + z * -0.4985314,
        x * -0.9692660 + y * 1.8760108 + z * 0.0415560,
        x * 0.0556434 + y * -0.2040259 + z * 1.0572252,
    ), axis=-1)
    srgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - 0.055)
    return np.clip(srgb * 255.0, 0, 255).astype(np.uint8)


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    lab = _srgb_to_lab(np.array([[rgb]], dtype=np.float32))[0, 0]
    return float(lab[0]), float(lab[1]), float(lab[2])


def feather(mask: np.ndarray, radius: int = 3) -> np.ndarray:
    """Blur only the mask edge; return float32 in 0..1."""
    arr = np.asarray(mask)
    if arr.ndim != 2:
        raise ValueError("mask must be 2-D")
    arr = np.clip(arr.astype(np.float32) / 255.0, 0.0, 1.0)
    if radius <= 0:
        return arr
    image = Image.fromarray((arr * 255).astype(np.uint8), mode="L")
    image = image.filter(ImageFilter.GaussianBlur(radius=max(0.5, float(radius))))
    return np.asarray(image).astype(np.float32) / 255.0


def exclude(mask: np.ndarray, *others: np.ndarray) -> np.ndarray:
    """Subtract protection masks (product, hands, face), keeping 0..255."""
    out = np.asarray(mask).astype(np.int16)
    for other in others:
        if other is None:
            continue
        out = out - np.asarray(other).astype(np.int16)
    return np.clip(out, 0, 255).astype(np.uint8)


def recolor_lab(
    frame_rgb: np.ndarray,
    mask: np.ndarray,
    color: str,
    *,
    strength: float = 0.85,
    feather_radius: int = 3,
    chroma_variation: float = 0.0,
    product_mask: np.ndarray | None = None,
    protect_masks: Iterable[np.ndarray] = (),
) -> np.ndarray:
    """Replace the garment chroma while keeping the source luminance.

    ``frame_rgb``: HxWx3 uint8 RGB.
    ``mask``: HxW uint8/float, 255/1.0 = garment.
    """
    frame = np.asarray(frame_rgb)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame_rgb must be HxWx3")
    if frame.shape[:2] != np.asarray(mask).shape[:2]:
        raise ValueError("mask size must match frame")

    cloth = np.asarray(mask).astype(np.uint8)
    protections = [product_mask, *protect_masks]
    cloth = exclude(cloth, *[p for p in protections if p is not None])
    alpha = feather(cloth, feather_radius) * float(np.clip(strength, 0.0, 1.0))
    alpha = alpha[..., None]

    source_lab = _srgb_to_lab(frame)
    target = rgb_to_lab(hex_to_rgb(color))
    recolored = source_lab.copy()
    # Keep L (shading), replace a/b with the target chroma.  A small amount of
    # source chroma variation keeps fabric texture from going flat.
    source_chroma = source_lab[..., 1:3] - source_lab[..., 1:3].mean(axis=(0, 1), keepdims=True)
    variation = float(np.clip(chroma_variation, 0.0, 1.0))
    recolored[..., 1] = float(target[1]) + source_chroma[..., 0] * variation
    recolored[..., 2] = float(target[2]) + source_chroma[..., 1] * variation
    recolored_rgb = _lab_to_srgb(recolored).astype(np.float32)

    out = frame.astype(np.float32) * (1.0 - alpha) + recolored_rgb * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def mask_coverage(mask: np.ndarray) -> float:
    arr = np.asarray(mask)
    return float((arr > 127).mean()) if arr.size else 0.0
