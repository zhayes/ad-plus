"""Collect reliability metrics for produced projects.

Reads a project workspace and reports what a production actually did: wall
clock, pipeline depth, tool calls, and the technical validity of the final
render. Used to build the verification table for the desktop MVP.

    python scripts/collect_run_metrics.py echo-ad type0-ad
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTS = REPO / "projects"


def _ffprobe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    try:
        return json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def _iso_to_ts(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def collect(project_id: str) -> dict:
    root = PROJECTS / project_id
    row: dict = {"project": project_id, "errors": []}
    if not root.is_dir():
        return {**row, "errors": ["missing project"]}

    marker = root / "project.json"
    if marker.is_file():
        data = json.loads(marker.read_text(encoding="utf-8"))
        row["title"] = data.get("title")
        row["pipeline"] = data.get("pipeline_type")

    checkpoints = sorted(root.glob("checkpoint_*.json"))
    row["checkpoints"] = len(checkpoints)
    row["stages"] = sorted(p.stem.replace("checkpoint_", "") for p in checkpoints)
    row["artifacts"] = len(list((root / "artifacts").glob("*.json"))) if (root / "artifacts").is_dir() else 0

    events = root / "events.jsonl"
    if events.is_file():
        rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
        row["tool_events"] = len(rows)
        stamps = [t for t in (_iso_to_ts(r.get("ts", "")) for r in rows) if t]
        if stamps:
            row["tool_span_s"] = round(max(stamps) - min(stamps), 1)
        row["tools"] = sorted({r.get("tool") for r in rows if r.get("tool")})

    renders = sorted(
        (p for p in root.rglob("*") if p.is_file() and p.suffix == ".mp4" and ".qa" not in str(p) and ".final_review" not in str(p)),
        key=lambda p: p.stat().st_mtime,
    )
    if renders:
        final = renders[-1]
        row["final"] = str(final.relative_to(REPO))
        row["final_mb"] = round(final.stat().st_size / 1_048_576, 2)
        start = marker.stat().st_mtime if marker.is_file() else None
        row["wall_minutes"] = round((final.stat().st_mtime - start) / 60, 1) if start else None
        info = _ffprobe(final)
        streams = info.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        row["video"] = bool(video)
        row["audio"] = bool(audio)
        if video:
            row["resolution"] = f"{video.get('width')}x{video.get('height')}"
            row["frames"] = video.get("nb_frames")
        row["duration_s"] = round(float(info.get("format", {}).get("duration", 0) or 0), 2)
    else:
        row["final"] = None
        row["errors"].append("no render")

    return row


def main(argv: list[str]) -> int:
    ids = argv[1:] or [p.name for p in sorted(PROJECTS.iterdir()) if p.is_dir()]
    rows = [collect(pid) for pid in ids]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
