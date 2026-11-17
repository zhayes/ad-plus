"""CLI for P3: shots.json -> final.mp4 -> qa.json.

    python -m adplus.recreate.finish_cli <skeleton.json> --script <script.json> \
        --shots <shots.json> --out <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adplus.recreate import assemble as assemble_mod
from adplus.recreate import qa as qa_mod


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adplus.recreate.finish_cli")
    parser.add_argument("skeleton")
    parser.add_argument("--script", required=True)
    parser.add_argument("--shots", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-voice", action="store_true", help="skip TTS (silent cut)")
    args = parser.parse_args(argv)

    skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    shots_doc = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    shots = shots_doc.get("shots") or shots_doc

    print("[assemble]", flush=True)
    plan = assemble_mod.assemble(skeleton, script, shots, args.out, voice=not args.no_voice)
    for row in plan["timeline"]:
        print(f"  {row['beat']:>3} {row['duration_s']:>5.2f}s {row['status']}", flush=True)
    print(f"  voice clips: {len(plan['voice'])}  subtitles: {len(plan['subtitles'])}")
    print(f"  final: {plan['output']} ({plan.get('duration_s')}s)")

    report = qa_mod.check(plan["output"], skeleton, script, timeline=plan)
    (Path(args.out) / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[qa]")
    for row in report["checks"]:
        print(f"  {row['status']:<5} {row['id']:<10} {row['label']}  {json.dumps(row['value'], ensure_ascii=False)}")
    print(f"  shippable: {report['summary']['shippable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
