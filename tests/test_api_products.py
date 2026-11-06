from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from adplus import products
from app.settings_server import app


class ProductApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="adplus-product-api-"))
        self.old = products.PRODUCTS
        products.PRODUCTS = self.tmp / "products"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        products.PRODUCTS = self.old

    def test_create_and_lock(self) -> None:
        response = self.client.post("/api/products", json={
            "name": "冰丝背心",
            "sku": "YAC-001",
            "hero_path": "uploads/hero.jpg",
            "locked": True,
            "rights": {"ai_reference_allowed": True, "commercial_use": True},
        })
        self.assertEqual(response.status_code, 200, response.text)
        product = response.json()["product"]
        self.assertTrue(product["locked"])
        self.assertTrue(product["rights"]["ai_reference_allowed"])
        self.assertEqual(self.client.get("/api/products").json()["products"][0]["sku"], "YAC-001")

    def test_locked_without_hero_rejected(self) -> None:
        response = self.client.post("/api/products", json={"name": "空商品", "locked": True})
        self.assertEqual(response.status_code, 400)
