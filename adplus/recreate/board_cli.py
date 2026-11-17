"""CLI for P2: build the cast sheet and one keyframe per beat.

    python -m adplus.recreate.board_cli <skeleton.json> --out <dir> \
        --script <script.json> --product <product.json>

Cost: one 9:16 image per beat plus two cast candidates (~$0.03 for 6 beats).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adplus.recreate import board as board_mod


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adplus.recreate.board_cli")
    parser.add_argument("skeleton", help="skeleton.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--script", help="script.json (optional, improves prompts)")
    parser.add_argument("--product", required=True, help="product JSON")
    parser.add_argument("--cast", help="reuse an existing cast image instead of generating")
    parser.add_argument("--per-beat", type=int, default=1, help="candidates per beat")
    parser.add_argument("--cast-count", type=int, default=2)
    args = parser.parse_args(argv)

    skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
    script = json.loads(Path(args.script).read_text(encoding="utf-8")) if args.script else None
    product = json.loads(Path(args.product).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cast_path = args.cast
    if not cast_path:
        print("[cast]", flush=True)
        cast = board_mod.build_cast(product, out, count=args.cast_count)
        cast_path = cast["chosen"]
        product = {**product, "cast": cast}
        (out / "cast.json").write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {cast_path}", flush=True)

    print("[board]", flush=True)
    board = board_mod.build_board(skeleton, script, product, out, cast_path=cast_path, per_beat=args.per_beat)
    for item in board["items"]:
        print(f"  {item['beat']:>3}  {item['status']:<10} {item.get('chosen') or item.get('images')}", flush=True)
    print(f"\nboard: {out / 'board.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
