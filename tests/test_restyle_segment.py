from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adplus.restyle import segment, store


class RestyleSegmentTest(unittest.TestCase):
    def test_backends_are_reported(self) -> None:
        rows = segment.available_backends()
        names = {row["name"] for row in rows}
        self.assertEqual(names, {"mediapipe", "onnx", "vision"})
        for row in rows:
            self.assertIn("available", row)

    def test_get_segmenter_is_optional(self) -> None:
        backend = segment.get_segmenter()
        if backend is not None:
            self.assertTrue(backend.available())
            self.assertIn(backend.name, {"mediapipe", "onnx", "vision"})

    def test_relative_paths_are_posix(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="adplus-restyle-path-"))
        old = store.WORKSPACE
        store.WORKSPACE = tmp
        try:
            target = tmp / "projects" / "x" / "restyle" / "source.mp4"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"x")
            self.assertEqual(store._rel(target), "projects/x/restyle/source.mp4")
            self.assertNotIn("\\", store._rel(target))
        finally:
            store.WORKSPACE = old


if __name__ == "__main__":
    unittest.main()
