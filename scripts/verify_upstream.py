#!/usr/bin/env python3
"""Assert the upstream surface Ad+ depends on is still there.

Run after `scripts/upstream.sh pull`. Fails loudly with the specific missing
piece instead of letting the app crash three layers down.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import adplus  # noqa: E402,F401  — puts vendor on sys.path
from adplus.paths import COMPOSER, PROJECTS, VENDOR  # noqa: E402

failures: list[str] = []


def check(label: str, fn) -> None:
    try:
        detail = fn()
        print(f"  ok   {label}{f' — {detail}' if detail else ''}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  FAIL {label} — {type(exc).__name__}: {exc}")


def main() -> int:
    print(f"vendor: {VENDOR}")
    print(f"composer: {COMPOSER}")
    print(f"projects: {PROJECTS}")

    def registry():
        from tools.tool_registry import registry as reg

        reg.discover()
        return f"{len(reg._tools)} tools"

    def estimate_hooks():
        from tools.tool_registry import registry as reg

        reg.discover()
        paid = [
            name
            for name, tool in reg._tools.items()
            if type(tool).estimate_cost.__qualname__.startswith(type(tool).__name__)
        ]
        if len(paid) < 50:
            raise RuntimeError(f"only {len(paid)} tools override estimate_cost")
        return f"{len(paid)} priced tools"

    def checkpoint_api():
        from lib.checkpoint import (  # noqa: F401
            get_completed_stages,
            get_latest_checkpoint,
            get_next_stage,
            write_checkpoint,
        )

        return "imports ok"

    def pipelines():
        files = sorted((VENDOR / "pipeline_defs").glob("*.yaml"))
        if not files:
            raise RuntimeError("no pipeline yaml")
        return f"{len(files)} pipelines"

    def composer():
        pkg = COMPOSER / "package.json"
        if not pkg.is_file():
            raise RuntimeError(f"missing {pkg}")
        return "package.json ok"

    def agent_docs():
        for name in ("AGENT_GUIDE.md", "skills", "pipeline_defs"):
            if not (VENDOR / name).exists():
                raise RuntimeError(f"missing {name}")
        return "docs/skills present"

    check("tool registry", registry)
    check("cost estimate hooks", estimate_hooks)
    check("lib.checkpoint API", checkpoint_api)
    check("pipeline definitions", pipelines)
    check("remotion composer", composer)
    check("agent docs & skills", agent_docs)

    print()
    if failures:
        print(f"{len(failures)} upstream contract(s) broken — Ad+ needs adaptation:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("upstream contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
