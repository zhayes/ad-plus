"""Region-aware OCR for burned-in captions and packaging text.

The restyle analyser only looks for red/yellow captions in the bottom 28% of a
frame.  Viral references use white text with black outline, top captions, and
product labels, so this module splits the frame into three bands, tries a
normal and an inverted threshold, and keeps whatever tesseract is confident
about.  Misses are acceptable; wrong text is not, so short/garbage hits are
dropped.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

TESSERACT = os.environ.get("ADPLUS_TESSERACT") or shutil.which("tesseract")
LANG = os.environ.get("ADPLUS_OCR_LANG", "chi_sim")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

BANDS = {"top": (0.0, 0.28), "middle": (0.28, 0.72), "bottom": (0.72, 1.0)}
CANON_WIDTH = 720


def available() -> bool:
    return bool(TESSERACT)


def read_frame(path: str | Path, *, min_conf: float = 30.0) -> dict[str, Any]:
    """Read text in three bands.

    ``min_conf`` is low on purpose: a heavy caption stroke can push a correct
    glyph to ~38 confidence ("袋" in the probe clip).  Low-confidence words are
    kept and the whole line is scored afterwards.
    """
    path = Path(path)
    if not available():
        return {"status": "unavailable", "regions": {}, "texts": []}
    from PIL import Image

    image = Image.open(path).convert("L")
    # Canonical width: thresholds were tuned (and verified) at 720px.  Feeding
    # a 960px frame changes the stroke-to-glyph ratio and costs accuracy.
    if image.width != CANON_WIDTH:
        image = image.resize((CANON_WIDTH, round(image.height * CANON_WIDTH / image.width)), Image.LANCZOS)
    width, height = image.size
    regions: dict[str, list[dict[str, Any]]] = {}
    for name, (top, bottom) in BANDS.items():
        crop = image.crop((0, int(height * top), width, int(height * bottom)))
        if crop.height < 12:
            regions[name] = []
            continue
        lines = _read_crop(crop, min_conf)
        regions[name] = lines

    texts = _dedupe([line["text"] for lines in regions.values() for line in lines])
    return {"status": "ok", "regions": regions, "texts": texts}


# Thresholds were tuned on burned-in captions (white with heavy black stroke)
# and packaging text (white on red).  110 keeps the glyph fill; 140 and "no
# threshold" win on thin white text; inversion handles dark-on-light labels.
VARIANTS = (
    (2, 110, False, 6),
    (2, 110, True, 6),
    (2, 140, False, 6),
    (2, 140, True, 6),
    (2, None, False, 6),
    (2, None, True, 6),
)


def _read_crop(crop, min_conf: float) -> list[dict[str, Any]]:
    """Run several pre-processing variants and keep the most believable one.

    Picking by "most characters" chose the wrong candidate in testing:
    a 6-variant grid read "安十九块九两" while the threshold-110 pass read the
    real line "两袋十九块九" with fewer characters.  Score by mean confidence
    instead, with a small bonus for producing more lines.
    """
    from PIL import Image, ImageOps

    best: list[dict[str, Any]] = []
    best_score = -1.0
    for scale, threshold, inverted, psm in VARIANTS:
        prepared = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        prepared = ImageOps.autocontrast(prepared)
        if inverted:
            prepared = ImageOps.invert(prepared)
        if threshold is not None:
            prepared = prepared.point(lambda p, t=threshold: 0 if p < t else 255)
        handle, name = tempfile.mkstemp(prefix="adplus_ocr_", suffix=".png")
        os.close(handle)
        path = Path(name)
        prepared.save(path)
        try:
            proc = subprocess.run(
                [TESSERACT, str(path), "stdout", "-l", LANG, "--psm", str(psm), "tsv"],
                capture_output=True,
                text=True,
                timeout=25,
                creationflags=_NO_WINDOW,
            )
            lines = [line for line in _parse_tsv(proc.stdout or "", min_conf) if _plausible(line["text"])]
        finally:
            path.unlink(missing_ok=True)
        if not lines:
            continue
        # Coverage beats raw confidence: dropping a low-confidence glyph is
        # what turned "两袋十九块九" into "两九块九".
        mean_conf = sum(line["conf"] for line in lines) / len(lines)
        # Per-line coverage: a global char count saturates at 8 and stops
        # rewarding the variant that recovered an extra glyph in one band.
        coverage = sum(min(len(line["text"]), 8) / 8.0 for line in lines) / len(lines)
        score = mean_conf * 0.5 + coverage * 50.0
        if score > best_score:
            best, best_score = lines, score
    return best


def _plausible(text: str) -> bool:
    """Reject OCR noise: require a CJK/ASCII mix with a real word in it."""
    if len(text) < 2:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if cjk == 0 and not any(ch.isdigit() for ch in text):
        return False
    if len(text) >= 4 and cjk / max(1, len(text)) < 0.4:
        return False
    return True


def _parse_tsv(tsv: str, min_conf: float) -> list[dict[str, Any]]:
    """Group tesseract word rows into lines, keeping only confident text."""
    rows = []
    for raw in tsv.splitlines()[1:]:
        parts = raw.split("\t")
        if len(parts) < 12:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        text = parts[11].strip()
        # CJK words are frequently one character ("袋", "九"); filtering by
        # length here silently dropped half of "两袋十九块九".
        if not text or conf < min_conf:
            continue
        rows.append({"text": text, "conf": conf, "left": int(parts[6] or 0), "top": int(parts[7] or 0)})
    if not rows:
        return []

    # Cluster words into lines by vertical proximity.  Bucketing tops with
    # integer division split "两" from the rest of its line whenever the glyph
    # sat 4px lower, which reordered the whole caption ("袋十九块九两").
    rows.sort(key=lambda r: (r["top"], r["left"]))
    clusters: list[dict[str, Any]] = []
    for row in rows:
        if clusters and abs(row["top"] - clusters[-1]["top"]) <= 20:
            clusters[-1]["rows"].append(row)
        else:
            clusters.append({"top": row["top"], "rows": [row]})

    lines: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster["rows"].sort(key=lambda r: r["left"])
        lines.append(_merge(cluster["rows"]))
    return [line for line in lines if line["text"]]


def _merge(words: list[dict[str, Any]]) -> dict[str, Any]:
    """Join words, then clean once — never per word (CJK words can be 1 char)."""
    text = _clean("".join(w["text"] for w in words))
    return {"text": text, "conf": round(sum(w["conf"] for w in words) / len(words), 1)}


def _clean(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9%¥￥\.\-:：!！?？]", "", text)
    return text if len(text) >= 2 else ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out
