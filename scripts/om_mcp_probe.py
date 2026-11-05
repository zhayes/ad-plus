"""Probe the OpenMontage MCP server the way a real host would.

Spawns `python -m om_mcp` over stdio, then drives the exact sequence an agent
host performs: initialize -> tools/list -> capabilities -> project -> a real
tool call -> async job. Any failure here would also be a failure inside Pi,
Claude Code or DSH, minus their transport quirks.

Run:  .venv/bin/python scripts/om_mcp_probe.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "projects" / "demos" / "renders" / "focusflow-pitch.mp4"
OUT_DIR = REPO / "projects" / "mcp-probe"


def show(label: str, value: object, limit: int = 700) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=2)
    print(f"\n--- {label} ---")
    print(text[:limit] + ("…" if len(text) > limit else ""))


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(
        command=str(REPO / ".venv" / "bin" / "python"),
        args=["-m", "om_mcp"],
        cwd=str(REPO),
        env={"OPENMONTAGE_PROJECTS_DIR": str(REPO / "projects")},
    )

    t0 = time.time()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            show("initialize", {
                "server": init.server_info.model_dump() if init.server_info else None,
                "protocol": init.protocol_version,
                "capabilities": list((init.capabilities.model_dump(exclude_none=True) if init.capabilities else {}).keys()),
                "startup_seconds": round(time.time() - t0, 1),
            })

            tools = await session.list_tools()
            show("tools/list", {
                "count": len(tools.tools),
                "names": [t.name for t in tools.tools],
            })

            caps = await session.call_tool("om_capabilities", {})
            payload = json.loads(caps.content[0].text)
            show("om_capabilities", {
                "runtimes": payload["composition_runtimes"],
                "capabilities": [
                    f"{c['capability']}: {c['configured']}/{c['total']}"
                    for c in payload["capabilities"]
                    if c["total"] and c["capability"] in
                    ("image_generation", "video_generation", "tts", "music_generation", "video_post")
                ],
            })

            listed = await session.call_tool("om_list_tools", {"capability": "video_post"})
            show("om_list_tools(video_post)", json.loads(listed.content[0].text))

            started = await session.call_tool(
                "om_start_project",
                {"project_id": "mcp-probe", "title": "MCP probe", "pipeline": "cinematic"},
            )
            show("om_start_project", json.loads(started.content[0].text))

            # A real, keyless tool call: trim 2s off a demo render.
            trimmed = OUT_DIR / "trim-copy.mp4"
            call = await session.call_tool(
                "om_call_tool",
                {
                    "tool": "video_trimmer",
                    "params": {
                        "operation": "cut",
                        "input_path": str(DEMO),
                        "output_path": str(trimmed),
                        "start_seconds": 0,
                        "end_seconds": 2,
                    },
                },
            )
            show("om_call_tool(video_trimmer.cut)", json.loads(call.content[0].text))
            print("output exists:", trimmed.exists(), trimmed.stat().st_size if trimmed.exists() else 0, "bytes")

            # Async path: same tool through submit/poll.
            job = await session.call_tool(
                "om_submit",
                {
                    "tool": "video_trimmer",
                    "params": {
                        "operation": "cut",
                        "input_path": str(DEMO),
                        "output_path": str(OUT_DIR / "trim-async.mp4"),
                        "start_seconds": 3,
                        "end_seconds": 5,
                    },
                },
            )
            job_id = json.loads(job.content[0].text)["job_id"]
            for _ in range(30):
                status = await session.call_tool("om_job", {"job_id": job_id})
                view = json.loads(status.content[0].text)
                if view["status"] != "running":
                    break
                await asyncio.sleep(1)
            show("om_submit -> om_job", view)

            arts = await session.call_tool("om_artifacts", {"project_id": "mcp-probe"})
            show("om_artifacts", json.loads(arts.content[0].text))

            bad = await session.call_tool("om_call_tool", {"tool": "does_not_exist", "params": {}})
            show("error path (isError)", {"is_error": bad.is_error, "text": bad.content[0].text})

    print(f"\nTOTAL {round(time.time() - t0, 1)}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
