"""Deterministic real-product plate compositing.

The model may generate a plausible garment but it will not preserve the SKU.
This module takes a real, locked product image and puts it on top of an
already generated host clip, then checks the visible label with tesseract.

It is intentionally not a generative step: no prompt, no model, no invented
text.  The product image is the source of truth.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from adplus import products, project_store
from adplus.paths import PROJECTS


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _resolve(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECTS.parent / path
    return path.resolve()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECTS.parent.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _takes_dir(project_id: str) -> Path:
    path = PROJECTS / project_id / "product_takes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(take: dict[str, Any]) -> dict[str, Any]:
    path = _takes_dir(str(take["project_id"])) / f"{take['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(take, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return take


def list_takes(project_id: str) -> list[dict[str, Any]]:
    directory = PROJECTS / project_id / "product_takes"
    if not directory.is_dir():
        return []
    rows = []
    for path in directory.glob("*.json"):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def _find_shot(project_id: str, version_id: str | None, shot_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project = project_store.load_project(project_id)
    if project is None:
        raise FileNotFoundError(project_id)
    version = project_store.load_version(project_id, version_id) if version_id else project_store.ensure_version(project_id)
    if version is None:
        raise FileNotFoundError("version not found")
    shot = next((s for s in version.get("shots") or [] if str(s.get("id")) == shot_id), None)
    if shot is None:
        raise KeyError(shot_id)
    return project, version, shot


def _ocr_label(image_path: Path) -> dict[str, Any]:
    exe = shutil.which("tesseract")
    if not exe:
        return {"status": "unknown", "text": "", "detail": "tesseract not installed"}
    try:
        proc = subprocess.run(
            [exe, str(image_path), "stdout", "--psm", "6", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = re.sub(r"\s+", " ", proc.stdout or "").strip()
        return {"status": "ok", "text": text, "detail": ""}
    except Exception as exc:
        return {"status": "unknown", "text": "", "detail": str(exc)[:200]}


def plan(
    project_id: str,
    *,
    shot_id: str,
    product_id: str | None = None,
    version_id: str | None = None,
    base_video_path: str | None = None,
    start_s: float = 2.0,
    end_s: float = 8.0,
    position: str = "bottom_right",
) -> dict[str, Any]:
    project, version, shot = _find_shot(project_id, version_id, shot_id)
    product_id = product_id or shot.get("product_id") or project.get("product_id")
    product = products.load_product(product_id) if product_id else None
    spec = shot.get("generation_spec") if isinstance(shot.get("generation_spec"), dict) else {}
    refs = shot.get("asset_refs") if isinstance(shot.get("asset_refs"), dict) else {}
    base = _resolve(str(base_video_path or spec.get("base_video_path") or refs.get("base_video") or ""))
    hero = _resolve(str(product.get("hero_path"))) if product and product.get("hero_path") else None

    blockers: list[str] = []
    warnings: list[str] = []
    if product is None:
        blockers.append("镜头没有绑定商品")
    else:
        if not product.get("locked"):
            blockers.append("商品未锁定，不能作为真实贴片")
        if not (product.get("rights") or {}).get("ai_reference_allowed"):
            blockers.append("商品未授权 AI 参考")
        if not hero or not hero.is_file():
            blockers.append("商品主图不存在")
    if not base or not base.is_file():
        blockers.append("缺少基础视频")

    output = PROJECTS / project_id / "renders" / f"product_plate_{shot_id}_{uuid.uuid4().hex[:6]}.mp4"
    take = {
        "id": f"pt_{uuid.uuid4().hex[:10]}",
        "project_id": project_id,
        "version_id": version["id"],
        "shot_id": shot_id,
        "product_id": product_id,
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "warnings": warnings,
        "product": products.product_snapshot(product_id),
        "input": {
            "base_video": _rel(base) if base else None,
            "product_image": _rel(hero) if hero else None,
            "start_s": float(start_s),
            "end_s": float(end_s),
            "position": position,
        },
        "output_path": _rel(output),
        "label_ocr": _ocr_label(hero) if hero else None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    return _save(take)


def _label_result(product: dict[str, Any], ocr: dict[str, Any] | None) -> dict[str, Any]:
    expected = str(product.get("label_text") or product.get("brand") or "").strip()
    text = str((ocr or {}).get("text") or "")
    if not expected:
        return {"verdict": "unknown", "expected": "", "actual": text, "detail": "商品没有配置标签文字"}
    if not ocr or ocr.get("status") != "ok":
        return {"verdict": "unknown", "expected": expected, "actual": text, "detail": "OCR 不可用"}
    ok = expected.lower().replace(" ", "") in text.lower().replace(" ", "")
    return {
        "verdict": "pass" if ok else "warn",
        "expected": expected,
        "actual": text[:200],
        "detail": "真实商品图标签匹配" if ok else "OCR 未匹配标签，需人工确认",
    }


def composite_files(
    base_video: str | Path,
    product_image: str | Path,
    output_path: str | Path,
    *,
    start_s: float = 2.0,
    end_s: float = 8.0,
    position: str = "bottom_right",
) -> dict[str, Any]:
    """Deterministic ffmpeg overlay; no AI, no network."""
    base = _resolve(str(base_video))
    hero = _resolve(str(product_image))
    output = _resolve(str(output_path))
    if not base or not hero or not output:
        raise ValueError("base/product/output path missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    with Image.open(hero) as img:
        width = 132
        height = round(img.height * width / img.width)
    start = max(0.0, float(start_s))
    end = max(start + 0.5, float(end_s))
    x = "20" if position.endswith("left") else "W-w-20"
    y = "H-h-150" if position.startswith("bottom") else "96"
    filter_complex = (
        f"[1:v]scale={width}:{height},format=rgba,pad={width + 8}:{height + 8}:4:4:color=white@0.85[plate];"
        f"[0:v][plate]overlay={x}:{y}:enable='between(t,{start},{end})'[v]"
    )
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error",
        "-i", str(base), "-i", str(hero),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    ok = proc.returncode == 0 and output.is_file()
    return {"success": ok, "output": _rel(output) if output.is_file() else None,
            "error": None if ok else (proc.stderr or "ffmpeg failed")[-1000:]}


def label_qa_for(product: dict[str, Any], image_path: str | Path) -> dict[str, Any]:
    """Public, deterministic label check used by compose/QA gates."""
    path = _resolve(str(image_path))
    if not path:
        return {"verdict": "unknown", "expected": str(product.get("label_text") or ""), "actual": "", "detail": "missing product image"}
    return _label_result(product, _ocr_label(path))


def execute(take: dict[str, Any]) -> dict[str, Any]:
    if take.get("status") != "ready":
        raise ValueError("take is blocked: " + "; ".join(take.get("blockers") or []))
    input_ = take.get("input") or {}
    base = _resolve(input_.get("base_video"))
    hero = _resolve(input_.get("product_image"))
    output = _resolve(take.get("output_path"))
    if not base or not hero or not output:
        raise ValueError("base/product/output path missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    with Image.open(hero) as img:
        width = 132
        height = round(img.height * width / img.width)
    start = max(0.0, float(input_.get("start_s") or 0))
    end = max(start + 0.5, float(input_.get("end_s") or start + 5))
    position = str(input_.get("position") or "bottom_left")
    x = "20" if position.endswith("left") else "W-w-20"
    y = "H-h-150" if position.startswith("bottom") else "96"
    filter_complex = (
        f"[1:v]scale={width}:{height},format=rgba,pad={width + 8}:{height + 8}:4:4:color=white@0.85[plate];"
        f"[0:v][plate]overlay={x}:{y}:enable='between(t,{start},{end})'[v]"
    )
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error",
        "-i", str(base), "-i", str(hero),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    ok = proc.returncode == 0 and output.is_file()
    take = copy.deepcopy(take)
    take["status"] = "done" if ok else "failed"
    product = take.get("product") or {}
    take["label_qa"] = _label_result(product, take.get("label_ocr"))
    take["result"] = {
        "success": ok,
        "error": None if ok else (proc.stderr or "ffmpeg failed")[-1000:],
        "output": _rel(output) if output.is_file() else None,
        "label_qa": take["label_qa"],
    }
    return _save(take)
