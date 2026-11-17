"""M-1 capability audit for Restyle.

Answers one question before writing any outfit code: what can the existing
OpenMontage tool registry already do, and what is actually missing?

Run:
    python scripts/restyle_capability_audit.py
    python scripts/restyle_capability_audit.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adplus.restyle.capabilities import audit  # noqa: E402


def main(argv: list[str]) -> int:
    result = audit()
    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"vendor: {result['vendor']}")
    print("\nRelevant tools:")
    for name, row in result["tools"].items():
        print(f"  {name:16} {row.get('status'):12} {row.get('provider') or '-'} {row.get('capabilities')}")
    print("\nvideo_edit providers:")
    for row in result["video_edit_tools"]:
        print(f"  {row}")
    print("\npipelines:")
    for row in result["pipelines"]:
        print(f"  {row.get('name'):22} {row.get('stages') or row.get('error')}")
    print("\ngaps:")
    for gap in result["gaps"]:
        print(f"  - {gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
