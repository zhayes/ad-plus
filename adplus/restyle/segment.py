"""Cross-platform person segmentation backends.

Windows is the primary target, so the default path must not depend on macOS
Vision.  This module keeps the compositor independent of the backend:

    frame (BGR ndarray) -> alpha mask (uint8, 0..255)

Backends, in preference order:

* ``mediapipe`` — Apache-2.0 selfie segmentation, Windows/macOS/Linux, fast.
* ``onnx`` — a user-supplied matting model via onnxruntime (MODNet/RVM etc.).
* ``vision`` — macOS-only quality boost, optional.

Hard shots (hand/product close-ups) still default to ``keep``; no backend is
allowed to pretend it can solve them.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Protocol


class Segmenter(Protocol):
    name: str

    def available(self) -> bool: ...

    def person_mask(self, frame: Any) -> Any: ...


class MediaPipeSegmenter:
    name = "mediapipe"

    def __init__(self) -> None:
        self._segmenter = None

    def available(self) -> bool:
        return importlib.util.find_spec("mediapipe") is not None

    def person_mask(self, frame: Any):
        import cv2
        import mediapipe as mp

        if self._segmenter is None:
            self._segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._segmenter.process(rgb)
        mask = (result.segmentation_mask * 255).astype("uint8")
        return mask


class OnnxSegmenter:
    """Placeholder for a bundled MODNet/RVM ONNX model.

    The model file is intentionally not shipped yet: pick a license-compatible
    checkpoint first (Windows-first, commercial distribution).  Set
    ``ADPLUS_SEGMENTER_MODEL`` to enable it later.
    """

    name = "onnx"

    def available(self) -> bool:
        model = os.environ.get("ADPLUS_SEGMENTER_MODEL", "")
        return bool(model) and importlib.util.find_spec("onnxruntime") is not None

    def person_mask(self, frame: Any):
        raise NotImplementedError("onnx segmenter model is not bundled yet")


class VisionSegmenter:
    """macOS-only optional backend; Windows must never require it."""

    name = "vision"

    def available(self) -> bool:
        return importlib.util.find_spec("Vision") is not None

    def person_mask(self, frame: Any):
        raise NotImplementedError("Vision frame wrapper is implemented in the P2 preview path")


_BACKENDS = {
    "mediapipe": MediaPipeSegmenter,
    "onnx": OnnxSegmenter,
    "vision": VisionSegmenter,
}


def available_backends() -> list[dict[str, Any]]:
    rows = []
    for name, factory in _BACKENDS.items():
        try:
            backend = factory()
            rows.append({"name": name, "available": bool(backend.available())})
        except Exception as exc:
            rows.append({"name": name, "available": False, "error": str(exc)[:120]})
    return rows


def get_segmenter(preferred: str | None = None) -> Segmenter | None:
    """Pick a backend without changing the compositor API.

    ``ADPLUS_SEGMENTER`` wins; otherwise prefer mediapipe everywhere, then the
    ONNX model.  Vision is only used on macOS when explicitly preferred.
    """
    order = [preferred] if preferred else []
    env = os.environ.get("ADPLUS_SEGMENTER", "")
    if env:
        order.append(env)
    order.extend(["mediapipe", "onnx"])
    if os.name != "nt":
        order.append("vision")
    for name in order:
        if not name:
            continue
        factory = _BACKENDS.get(name)
        if factory is None:
            continue
        backend = factory()
        if backend.available():
            return backend
    return None
