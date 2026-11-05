#!/usr/bin/env python3
"""Rewrite absolute paths recorded before the workspace move.

Session transcripts and config.json store absolute paths from the old
single-repo layout (`/Users/chad/OpenMontage/projects/...`). After splitting
Ad+ into its own workspace those files must point at the new root, otherwise
artifact thumbnails 404.

    scripts/migrate_paths.py --dry-run
    scripts/migrate_paths.py            # writes, after backing up to *.bak
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

OLD = "/Users/chad/OpenMontage"
NEW = "/Users/chad/AdPlus"
APP_DATA = Path.home() / "Library" / "Application Support" / "Ad+"


def rewrite(path: Path, dry: bool) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    if OLD not in text:
        return 0
    hits = text.count(OLD)
    if not dry:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets: list[Path] = list((APP_DATA / "sessions").glob("*.jsonl"))
    config = APP_DATA / "config.json"
    if config.is_file():
        targets.append(config)

    total = 0
    for path in targets:
        hits = rewrite(path, args.dry_run)
        if hits:
            total += hits
            print(f"{'would rewrite' if args.dry_run else 'rewrote'} {hits:4d}  {path.name}")
    print(f"\n{'would touch' if args.dry_run else 'touched'} {total} references")
    if not args.dry_run and total:
        print("backups written next to the originals (*.bak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
