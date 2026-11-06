"""Locked product assets for commerce ads.

The model may invent a pleasant garment; it will not preserve a real SKU,
label or packaging.  A product record is therefore the opposite of a prompt:
it is a frozen, rights-aware reference that a shot can bind to.

    products/<id>.json

Hero and detail images stay in the normal uploads/assets store; this record
stores workspace-relative paths and the fields a quote/QA pass needs.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from adplus.paths import PRODUCTS

PRODUCT_STATUSES = ("draft", "locked", "archived")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _check_id(value: str) -> str:
    value = (value or "").strip()
    if not _ID_RE.match(value):
        raise ValueError("product id must contain only letters, digits, dot, dash, underscore")
    return value


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _dir(create: bool = False) -> Path:
    if create:
        PRODUCTS.mkdir(parents=True, exist_ok=True)
    return PRODUCTS


def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    product = copy.deepcopy(data)
    product.setdefault("id", f"prod_{uuid.uuid4().hex[:8]}")
    product["name"] = str(product.get("name") or "").strip()
    product["sku"] = str(product.get("sku") or "").strip()
    product["brand"] = str(product.get("brand") or "").strip()
    product["label_text"] = str(product.get("label_text") or "").strip()
    product["category"] = str(product.get("category") or "").strip()
    product["hero_path"] = product.get("hero_path") or None
    product["detail_paths"] = [str(p) for p in (product.get("detail_paths") or []) if str(p).strip()]
    product["tags"] = [str(t) for t in (product.get("tags") or []) if str(t).strip()]
    status = str(product.get("status") or "draft")
    product["status"] = status if status in PRODUCT_STATUSES else "draft"
    product["locked"] = bool(product.get("locked"))
    rights = product.get("rights") if isinstance(product.get("rights"), dict) else {}
    product["rights"] = {
        "commercial_use": bool(rights.get("commercial_use")),
        "ai_reference_allowed": bool(rights.get("ai_reference_allowed")),
        "note": str(rights.get("note") or ""),
    }
    product.setdefault("created_at", _now())
    product.setdefault("updated_at", product["created_at"])
    return product


def list_products(include_archived: bool = False) -> list[dict[str, Any]]:
    directory = _dir()
    if not directory.is_dir():
        return []
    rows = []
    for path in directory.glob("*.json"):
        product = _read(path)
        if not product:
            continue
        product = _normalise(product)
        if not include_archived and product.get("status") == "archived":
            continue
        rows.append(product)
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows


def load_product(product_id: str) -> dict[str, Any] | None:
    data = _read(_dir() / f"{_check_id(product_id)}.json")
    return _normalise(data) if data else None


def save_product(data: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
    if not product_id and data.get("id"):
        product_id = _check_id(str(data["id"]))
    existing = load_product(product_id) if product_id else None
    product = _normalise({**(existing or {}), **copy.deepcopy(data)})
    if product_id:
        product["id"] = _check_id(product_id)
    else:
        product["id"] = f"prod_{uuid.uuid4().hex[:8]}"
    if not product["name"]:
        raise ValueError("product name required")
    if product["locked"] and not product.get("hero_path"):
        raise ValueError("locked product needs hero_path")
    product["updated_at"] = _now()
    _atomic(_dir(create=True) / f"{product['id']}.json", product)
    return product


def delete_product(product_id: str) -> bool:
    path = _dir() / f"{_check_id(product_id)}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def product_snapshot(product_id: str | None) -> dict[str, Any] | None:
    if not product_id:
        return None
    product = load_product(product_id)
    if product is None:
        return None
    snapshot = copy.deepcopy(product)
    snapshot["captured_at"] = _now()
    return snapshot
