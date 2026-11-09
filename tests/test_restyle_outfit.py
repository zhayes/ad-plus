from __future__ import annotations

import unittest

import numpy as np

from adplus.restyle import outfit


class RestyleOutfitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = np.full((64, 64, 3), 255, dtype=np.uint8)
        self.frame[16:48, 16:48] = (200, 30, 30)  # red garment in the center
        self.mask = np.zeros((64, 64), dtype=np.uint8)
        self.mask[16:48, 16:48] = 255

    def test_recolor_changes_garment_only(self) -> None:
        out = outfit.recolor_lab(self.frame, self.mask, "#1F2937", strength=1.0, feather_radius=0)
        center = out[32, 32].astype(int)
        self.assertGreater(center[2], center[0])  # blue > red
        self.assertEqual(tuple(out[0, 0]), (255, 255, 255))
        self.assertEqual(tuple(out[63, 63]), (255, 255, 255))

    def test_product_mask_is_untouched(self) -> None:
        product = np.zeros((64, 64), dtype=np.uint8)
        product[28:36, 28:36] = 255
        out = outfit.recolor_lab(
            self.frame, self.mask, "#1F2937", strength=1.0, feather_radius=0, product_mask=product
        )
        self.assertEqual(tuple(out[32, 32]), tuple(self.frame[32, 32]))
        self.assertGreater(out[20, 20][2], out[20, 20][0])

    def test_feather_returns_soft_alpha(self) -> None:
        alpha = outfit.feather(self.mask, 3)
        self.assertEqual(alpha.shape, self.mask.shape)
        self.assertGreater(float(alpha.max()), 0.9)
        self.assertGreater(float(alpha[16, 32]), 0.0)
        self.assertLess(float(alpha[16, 32]), 1.0)

    def test_coverage(self) -> None:
        self.assertAlmostEqual(outfit.mask_coverage(self.mask), 0.25, places=2)


if __name__ == "__main__":
    unittest.main()
