"""Probe per-shot speech mode (on_camera / voiceover / no_speech).

Uses local audio RMS + MediaPipe face detection. No cloud/ASR required.

    python scripts/restyle_speech_probe.py projects/project-f54a
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adplus.paths import PROJECTS  # noqa: E402
from adplus.restyle import speech  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: restyle_speech_probe.py <project_id|project_dir>", file=sys.stderr)
        return 2
    project = Path(argv[0])
    if not project.is_dir():
        project = PROJECTS / argv[0]
    root = project / "restyle"
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    blueprint = json.loads((root / "blueprint.json").read_text(encoding="utf-8"))
    video = PROJECTS.parent / source["path"]
    rows = speech.analyze_shots(str(video), blueprint.get("shots") or [])
    (root / "speech.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in rows:
        print(f"{row['shot_id']}: {row['mode']:10} conf={row['confidence']:.2f} face={row.get('face_ratio')} mouth={row['mouth_motion']}")
    print(f"wrote {root / 'speech.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
