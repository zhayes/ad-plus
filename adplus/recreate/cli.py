"""Command line entry point for the P0 recreate analyser.

    python -m adplus.recreate.cli <video> --out uploads/recreate/p0/name

Prints a short human summary and writes ``skeleton.json`` plus beat frames.
No generation, no cost beyond the optional VLM tagging (~$0.01 per video).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adplus.recreate import extract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adplus.recreate.cli")
    parser.add_argument("video", help="reference video path or URL-less local file")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--asr-model", default=None, help="faster-whisper size (base/small/medium)")
    parser.add_argument("--language", default=None, help="force ASR language, e.g. zh")
    parser.add_argument("--max-frames", type=int, default=8, help="frames sent to the VLM")
    parser.add_argument("--no-vision", action="store_true", help="skip VLM tagging (offline run)")
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR")
    args = parser.parse_args(argv)

    skeleton = extract.analyze(
        args.video,
        out_dir=args.out,
        asr_model=args.asr_model,
        language=args.language,
        max_frames=args.max_frames,
        with_vision=not args.no_vision,
        with_ocr=not args.no_ocr,
        progress=lambda message: print(f"[{message}]", flush=True),
    )
    print(json.dumps(_summary(skeleton), ensure_ascii=False, indent=2))
    print(f"\nskeleton: {Path(args.out) / 'skeleton.json'}")
    return 0


def _summary(skeleton: dict) -> dict:
    beats = skeleton.get("beats") or []
    return {
        "source": skeleton["source"]["path"],
        "duration_s": skeleton["source"]["duration_s"],
        "cuts": skeleton.get("cuts_s"),
        "shots": len(skeleton.get("shots") or []),
        "beats": len(beats),
        "lines": len((skeleton.get("speech") or {}).get("segments") or []),
        "speakers": (skeleton.get("speech") or {}).get("speakers", {}).get("labels"),
        "product": skeleton.get("product_slot"),
        "confidence": skeleton.get("confidence"),
        "elapsed_s": skeleton.get("elapsed_s"),
        "beat_table": [
            {
                "id": beat["id"],
                "time": f"{beat['start_s']:.1f}-{beat['end_s']:.1f}",
                "function": beat["function"],
                "text": " / ".join(line["text"] for line in beat["dialogue"])[:60],
                "visual": (beat.get("visual") or {}).get("action"),
                "motion": _motion_at(skeleton, beat["start_s"]),
            }
            for beat in beats
        ],
    }


def _motion_at(skeleton: dict, start: float) -> str | None:
    """Beat -> shot-level motion label (beats live inside shots, not on edges)."""
    for shot in ((skeleton.get("audio_bed") or {}).get("motion") or {}).get("per_shot", []):
        if shot["start"] - 0.01 <= start < shot["end"]:
            return shot.get("level")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
