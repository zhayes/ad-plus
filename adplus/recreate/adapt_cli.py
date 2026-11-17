"""CLI for P1: skeleton -> gag_spec -> script.

    python -m adplus.recreate.adapt_cli <skeleton.json> --out <dir>
    python -m adplus.recreate.adapt_cli <skeleton.json> --out <dir> --product chickpea.json

``--product`` accepts a JSON file (or inline flags).  Without it only
``gag_spec.json`` is written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from adplus.recreate import gag as gag_mod
from adplus.recreate import script as script_mod


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adplus.recreate.adapt_cli")
    parser.add_argument("skeleton", help="skeleton.json produced by adplus.recreate.cli")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--product", help="product JSON file")
    parser.add_argument("--name", help="product name (inline)")
    parser.add_argument("--price", help="original price placeholder")
    parser.add_argument("--promo-price", dest="promo_price", help="promo price placeholder")
    parser.add_argument("--model", help="override the text model")
    args = parser.parse_args(argv)

    skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    spec = gag_mod.extract(skeleton, model=args.model)
    (out / "gag_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(_gag_summary(spec), ensure_ascii=False, indent=2))

    product = _product(args)
    if product:
        script = script_mod.adapt(skeleton, spec, product, model=args.model)
        (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(_script_summary(script), ensure_ascii=False, indent=2))

    print(f"\noutput: {out}")
    return 0


def _product(args) -> dict[str, Any] | None:
    if args.product:
        return json.loads(Path(args.product).read_text(encoding="utf-8"))
    if args.name:
        return {"name": args.name, "price": args.price, "promo_price": args.promo_price}
    return None


def _gag_summary(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "mechanism": spec["mechanism"],
        "label": spec["mechanism_label"],
        "confidence": spec["confidence"],
        "degraded": (spec.get("source") or {}).get("degraded"),
        "must_keep": [f"{item['id']} {item['text']} ({item.get('beat')})" for item in spec["must_keep"]],
        "punchline": spec["timing"],
    }


def _script_summary(script: dict[str, Any]) -> dict[str, Any]:
    return {
        "beats": [
            {
                "id": beat["id"],
                "fit": beat["fit"],
                "chars": f"{beat['chars']}/{beat['max_chars']}",
                "est_s": beat["est_s"],
                "lines": " / ".join(f"[{line['speaker']}] {line['text']}" for line in beat["lines"]),
            }
            for beat in script["beats"]
        ],
        "totals": script["totals"],
        "degraded": (script.get("source") or {}).get("degraded"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
