"""OpenMontage MCP server (stdio).

One bridge, every agent host: Pi 1.x, Claude Code, Cursor, DeepSeek Harness all
speak MCP, so this module is the only integration surface OpenMontage needs.

Run it directly:

    .venv/bin/python -m om_mcp

Host config (any MCP client):

    {"mcpServers": {"openmontage": {
        "command": "<repo>/.venv/bin/python",
        "args": ["-m", "om_mcp"],
        "cwd": "<repo>"
    }}}

Design rules baked in here:

* **Facade, not dump.** The registry exposes ~200 tools. Exposing all of them
  would flood the model's tool list, so this server publishes a small curated
  surface plus `om_call_tool` / `om_list_tools` for everything else.
* **Submit/poll for slow work.** Image, video, TTS and render calls run for
  minutes; MCP clients time out far sooner. Those go through `om_submit` +
  `om_job`.
* **Secrets come from the environment.** `om_reload_env` re-reads a JSON
  secrets file so a desktop settings page can hot-apply keys without touching
  the repository's `.env` (the tools' own `.env` loader never overwrites an
  existing environment variable, so injected values win).
"""

from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

import adplus  # noqa: F401  — puts the vendor checkout on sys.path
from adplus.paths import COMPOSER as _COMPOSER_DIR
from adplus.paths import PROJECTS as PROJECTS_DIR
from adplus.paths import VENDOR as REPO_ROOT
SECRETS_FILE = os.environ.get("OPENMONTAGE_SECRETS_FILE")

_registry: Any = None
_registry_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()

SERVER_NAME = "openmontage"
SERVER_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #


def _registry_or_raise() -> Any:
    global _registry
    with _registry_lock:
        if _registry is None:
            from tools.tool_registry import registry as reg

            reg.discover()
            _registry = reg
        return _registry


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _text(payload: Any) -> types.CallToolResult:
    body = payload if isinstance(payload, str) else _dump(payload)
    return types.CallToolResult(content=[types.TextContent(type="text", text=body)])


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        isError=True,
    )


def load_secrets(path: str | None = None) -> int:
    """Merge a JSON secrets file into the environment. Returns how many applied."""
    target = path or SECRETS_FILE
    if not target:
        return 0
    file = Path(target)
    if not file.is_file():
        return 0
    data = json.loads(file.read_text(encoding="utf-8"))
    applied = 0
    for key, value in data.items():
        if not key or not value:
            continue
        if key in os.environ:  # same precedence rule as tools/tool_registry.py
            continue
        os.environ[key] = str(value)
        applied += 1
    return applied


_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _ffprobe(path: Path) -> dict[str, Any] | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None


def verify_artifacts(artifacts: Any) -> list[str]:
    """Check that produced media files are real.

    Several tools report `success: true` while writing an empty or
    stream-less file (a `video_trimmer` cut at t=0 with stream copy is the
    known case). The agent must not be able to build the next stage on top of
    a broken asset, so every media artifact is probed here and a failure
    demotes the whole call.
    """
    if os.environ.get("OPENMONTAGE_VERIFY_ARTIFACTS", "1") in {"0", "false", "no"}:
        return []
    problems: list[str] = []
    for item in artifacts or []:
        raw = item.get("path") if isinstance(item, dict) else item
        if not raw:
            continue
        path = Path(str(raw))
        if not path.exists():
            problems.append(f"{path.name}: missing")
            continue
        size = path.stat().st_size
        if size == 0:
            problems.append(f"{path.name}: empty file")
            continue
        suffix = path.suffix.lower()
        if suffix not in _VIDEO_EXT | _AUDIO_EXT | _IMAGE_EXT:
            continue
        info = _ffprobe(path)
        if info is None:
            problems.append(f"{path.name}: not decodable by ffprobe")
            continue
        streams = info.get("streams") or []
        kinds = {s.get("codec_type") for s in streams}
        if suffix in _VIDEO_EXT and "video" not in kinds:
            problems.append(f"{path.name}: no video stream (audio only?)")
        elif suffix in _AUDIO_EXT and "audio" not in kinds:
            problems.append(f"{path.name}: no audio stream")
        elif suffix in _IMAGE_EXT and not streams:
            problems.append(f"{path.name}: no image stream")
    return problems


def _tool_result(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute one registry tool and normalise its result for JSON transport."""
    reg = _registry_or_raise()
    tool = reg.get(tool_name)
    if tool is None:
        raise KeyError(f"unknown tool {tool_name!r} (try om_list_tools)")
    result = tool.execute(params)
    artifacts = getattr(result, "artifacts", None) or []
    payload = {
        "tool": tool_name,
        "success": bool(getattr(result, "success", False)),
        "data": getattr(result, "data", None),
        "error": getattr(result, "error", None),
        "artifacts": artifacts,
        "cost_usd": getattr(result, "cost_usd", None),
        "duration_seconds": getattr(result, "duration_seconds", None),
    }
    if payload["success"]:
        problems = verify_artifacts(artifacts)
        if problems:
            payload["success"] = False
            payload["error"] = "artifact verification failed: " + "; ".join(problems)
            payload["verification_failures"] = problems
    return payload


def _start_job(tool_name: str, params: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "tool": tool_name,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "result": None,
            "error": None,
        }

    def worker() -> None:
        try:
            payload = _tool_result(tool_name, params)
            with _jobs_lock:
                job = _jobs[job_id]
                job["result"] = payload
                job["status"] = "succeeded" if payload["success"] else "failed"
                job["error"] = payload.get("error")
                job["finished_at"] = time.time()
        except Exception as exc:  # keep the job registry the source of truth
            with _jobs_lock:
                job = _jobs[job_id]
                job["status"] = "failed"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["finished_at"] = time.time()

    threading.Thread(target=worker, name=f"om-job-{job_id}", daemon=True).start()
    return job_id


def _job_view(job_id: str) -> dict[str, Any]:
    from adplus import jobs as job_store

    for record in job_store.list_jobs(limit=200):
        if record.get("id") == job_id:
            if record.get("status") == "running" and record.get("started_at"):
                try:
                    record["elapsed_seconds"] = round(
                        time.time() - time.mktime(time.strptime(record["started_at"][:19], "%Y-%m-%dT%H:%M:%S")), 1
                    )
                except Exception:
                    pass
            return record
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job {job_id!r}")
        view = dict(job)
    if view["status"] == "running" and view["started_at"]:
        view["elapsed_seconds"] = round(time.time() - view["started_at"], 1)
    return view


# --------------------------------------------------------------------------- #
# facade tool implementations
# --------------------------------------------------------------------------- #


def om_capabilities() -> dict[str, Any]:
    summary = _registry_or_raise().provider_menu_summary()
    return {
        "composition_runtimes": summary.get("composition_runtimes"),
        "capabilities": [
            {
                "capability": item.get("capability"),
                "configured": item.get("configured"),
                "total": item.get("total"),
                "providers": item.get("providers") or item.get("available") or [],
            }
            for item in summary.get("capabilities", [])
        ],
        "setup_offers": summary.get("setup_offers", [])[:12],
        "runtime_warnings": summary.get("runtime_warnings", []),
    }


def om_list_tools(capability: str | None = None, query: str | None = None) -> dict[str, Any]:
    reg = _registry_or_raise()
    rows = []
    for name, tool in reg._tools.items():  # noqa: SLF001 - public listing has no filter
        info = tool.get_info()
        cap = info.get("capability")
        if capability and cap != capability:
            continue
        if query and query.lower() not in f"{name} {info.get('provider')}".lower():
            continue
        rows.append(
            {
                "name": name,
                "capability": cap,
                "provider": info.get("provider"),
                "status": info.get("status"),
                "best_for": (info.get("best_for") or [])[:3],
            }
        )
    rows.sort(key=lambda r: (r["capability"] or "", r["name"]))
    return {"count": len(rows), "tools": rows}


def om_start_project(project_id: str, title: str, pipeline: str = "cinematic") -> dict[str, Any]:
    from lib.checkpoint import init_project

    path = init_project(project_id, title=title, pipeline_type=pipeline)
    root = Path(path)
    return {
        "project_id": project_id,
        "root": str(root),
        "pipeline": pipeline,
        "expected_paths": {
            "artifacts": str(root / "artifacts"),
            "assets": str(root / "assets"),
            "renders": str(root / "renders"),
        },
    }


def _project_pipeline(project_id: str) -> str | None:
    """Read pipeline_type from the project marker so callers need not repeat it."""
    marker = PROJECTS_DIR / project_id / "project.json"
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("pipeline_type")
    except (OSError, json.JSONDecodeError):
        return None


def om_checkpoint(project_id: str, pipeline: str | None = None) -> dict[str, Any]:
    from lib.checkpoint import get_completed_stages, get_latest_checkpoint, get_next_stage

    pipeline = pipeline or _project_pipeline(project_id)
    return {
        "project_id": project_id,
        "pipeline": pipeline,
        "completed_stages": get_completed_stages(PROJECTS_DIR, project_id, pipeline),
        "next_stage": get_next_stage(PROJECTS_DIR, project_id, pipeline),
        "latest": get_latest_checkpoint(PROJECTS_DIR, project_id),
    }


def om_write_checkpoint(
    project_id: str,
    stage: str,
    status: str = "completed",
    artifacts: dict[str, Any] | None = None,
    pipeline: str | None = None,
    human_approved: bool = False,
    review: dict[str, Any] | None = None,
    cost_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Persist a stage checkpoint.

    Without this the agent has to write Python by hand to advance the
    pipeline — which is how the first end-to-end run bypassed the contract.
    """
    from lib.checkpoint import write_checkpoint

    path = write_checkpoint(
        PROJECTS_DIR,
        project_id,
        stage,
        status,
        artifacts or {},
        pipeline_type=pipeline,
        human_approved=human_approved,
        review=review,
        cost_snapshot=cost_snapshot,
        metadata=metadata,
        error=error,
    )
    return {
        "project_id": project_id,
        "stage": stage,
        "status": status,
        "path": str(path),
    }


def om_artifacts(project_id: str) -> dict[str, Any]:
    root = PROJECTS_DIR / project_id
    if not root.is_dir():
        raise FileNotFoundError(f"no project at {root}")
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == "history":
            continue
        files.append({"path": str(rel), "bytes": path.stat().st_size})
    return {"project_id": project_id, "root": str(root), "files": files}


def om_reload_env() -> dict[str, Any]:
    applied = load_secrets()
    return {"secrets_file": SECRETS_FILE, "applied": applied}




# --------------------------------------------------------------------------- #
# rendering (atelier compositions)
# --------------------------------------------------------------------------- #

_ENTRY_CANDIDATES = ("index.tsx", "index.ts", "src/index.tsx", "src/index.ts", "Root.tsx")


def _node_env() -> dict[str, str]:
    """PATH for Node tooling, including a guest Finder launch (no shell profile)."""
    env = dict(os.environ)
    extra = [
        str(Path.home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.is_dir():
        extra += [str(p / "bin") for p in sorted(nvm.iterdir(), reverse=True) if (p / "bin").is_dir()]
    env["PATH"] = ":".join(extra + [env.get("PATH", "")])
    env.setdefault("npm_config_cache", str(Path.home() / ".cache" / "adplus-npm"))
    env.setdefault("CI", "1")
    return env


def _find_entry(project_root: Path) -> Path | None:
    for name in _ENTRY_CANDIDATES:
        candidate = project_root / name
        if candidate.is_file():
            return candidate
    return None


def _list_compositions(entry: Path) -> list[str]:
    npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
    proc = subprocess.run(
        [npx, "remotion", "compositions", str(entry)],
        cwd=str(_COMPOSER_DIR),
        capture_output=True,
        text=True,
        timeout=240,
        env=_node_env(),
    )
    ids: list[str] = []
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("Bundling", "Bundled", "The following", "⚡")):
            continue
        parts = stripped.split()
        if parts and parts[0][:1].isalpha() and len(parts) >= 4:
            ids.append(parts[0])
    return ids


def om_render(
    project_id: str,
    composition: str | None = None,
    entry: str | None = None,
    output: str | None = None,
    timeout_seconds: int = 600,
    wait: bool = True,
) -> dict[str, Any]:
    """Render a project composition. `wait=False` returns a job id to poll."""
    from adplus import jobs as job_store

    project_root = PROJECTS_DIR / project_id
    if not project_root.is_dir():
        raise FileNotFoundError(f"no project at {project_root}")
    entry_path = (project_root / entry) if entry else _find_entry(project_root)
    if not entry_path or not Path(entry_path).is_file():
        raise FileNotFoundError(
            f"no Remotion entry in {project_root} (looked for {', '.join(_ENTRY_CANDIDATES)})"
        )
    comp_id = composition
    if not comp_id:
        found = _list_compositions(Path(entry_path))
        if not found:
            raise RuntimeError("remotion compositions returned no composition id")
        comp_id = found[0]

    if output:
        out_path = Path(output).expanduser()
        if not out_path.is_absolute():
            out_path = PROJECTS_DIR.parent / out_path
    else:
        out_path = project_root / "renders" / f"{project_id}-{comp_id}.mp4"
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    job = job_store.start("render", project_id, output=str(out_path), composition=comp_id)
    cmd = _render_command(Path(entry_path), comp_id, out_path)
    thread = threading.Thread(
        target=_run_render_job, args=(job, cmd, out_path, int(timeout_seconds)),
        name=f"render-{job['id']}", daemon=True,
    )
    thread.start()
    if not wait:
        return {
            "rendered": None,
            "job_id": job["id"],
            "status": "running",
            "composition": comp_id,
            "output": str(out_path),
            "poll_with": "om_job",
        }
    thread.join(timeout=max(5, int(timeout_seconds)) + 30)
    final = job_store.get(project_id, job["id"]) or job
    return {
        "rendered": final.get("status") == "done",
        "job_id": final.get("id"),
        "status": final.get("status"),
        "composition": comp_id,
        "output": final.get("output"),
        "elapsed_seconds": final.get("elapsed_seconds"),
        "verification_failures": final.get("verification_failures") or [],
        "error": final.get("error"),
        "cancelled": final.get("status") == "cancelled",
    }


def _render_command(entry_path: Path, comp_id: str, out_path: Path) -> list[str]:
    npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
    cmd = [npx, "remotion", "render", str(entry_path), comp_id, str(out_path), "--log=info"]
    public_dir = (out_path.parent.parent / "public").resolve()
    if public_dir.is_dir():
        cmd += ["--public-dir", str(public_dir)]
    return cmd


def _run_render_job(job: dict[str, Any], cmd: list[str], out_path: Path, timeout_seconds: int) -> None:
    """Own the render process: progress → job file, cancel → killpg."""
    from adplus import jobs as job_store

    started = time.time()
    # A previous render of the same composition must not be mistaken for this
    # job's output (cancel + verify would otherwise report a false success).
    try:
        if out_path.exists():
            out_path.unlink()
    except OSError:
        pass
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(_COMPOSER_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=_node_env(), start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001 - never leave a job "running" forever
        job_store.finish(job, "failed", error=f"could not start render: {type(exc).__name__}: {exc}")
        return
    job["pid"] = proc.pid
    job_store.update(job, pid=proc.pid)

    progress_re = re.compile(r"(?:Rendered|Rendering frames)\s+(\d+)\s*/\s*(\d+)")
    tail: list[str] = []
    cancelled = False
    last_write = 0.0

    def tick(done: int, total: int) -> None:
        nonlocal last_write
        now = time.time()
        if now - last_write < 1.0 and done not in (0, total):
            return
        last_write = now
        job_store.update(
            job, frames_done=done, frames_total=total,
            progress=round(min(1.0, done / total), 4) if total else 0.0,
            elapsed_seconds=round(now - started, 1),
        )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            tail.append(line.rstrip())
            if len(tail) > 20:
                tail.pop(0)
            match = progress_re.search(line)
            if match:
                tick(int(match.group(1)), int(match.group(2)))
            if job_store.cancel_requested(job["project_id"], job["id"]):
                cancelled = True
                _kill_tree(proc)
                break
            if time.time() - started > timeout_seconds:
                _kill_tree(proc)
                job_store.update(job, log_tail=tail)
                job_store.finish(job, "failed", error=f"render exceeded {timeout_seconds}s budget")
                return
        proc.wait(timeout=30)
    except Exception as exc:  # noqa: BLE001 - a job must never crash the MCP server
        _kill_tree(proc)
        job_store.finish(job, "failed", error=f"{type(exc).__name__}: {exc}", output=str(out_path))
        return

    elapsed = round(time.time() - started, 1)
    if cancelled:
        job_store.update(job, log_tail=tail, elapsed_seconds=elapsed)
        # A cancel that lands after the last frame was written should not throw
        # away a perfectly good file.
        problems = verify_artifacts([str(out_path)])
        fresh = out_path.is_file() and out_path.stat().st_mtime >= started
        if fresh and not problems:
            job_store.finish(job, "done", output=str(out_path))
        else:
            job_store.finish(job, "cancelled", output=str(out_path))
        return
    problems = verify_artifacts([str(out_path)])
    ok = proc.returncode == 0 and not problems
    job_store.update(job, log_tail=tail, elapsed_seconds=elapsed, verification_failures=problems)
    if ok:
        job_store.finish(job, "done", output=str(out_path))
    else:
        job_store.finish(
            job, "failed",
            error="; ".join(problems) or (tail[-1] if tail else "render failed"),
            output=str(out_path),
        )


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the whole render tree (npx → node → chrome)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except OSError:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except OSError:
            proc.kill()


# --------------------------------------------------------------------------- #
# quote + human gate
# --------------------------------------------------------------------------- #
def om_preview(
    project_id: str,
    frames: list[int] | None = None,
    composition: str | None = None,
    entry: str | None = None,
    width: int = 480,
) -> dict[str, Any]:
    """Render a handful of stills so a human can approve the look cheaply."""
    project_root = PROJECTS_DIR / project_id
    if not project_root.is_dir():
        raise FileNotFoundError(f"no project at {project_root}")
    entry_path = (project_root / entry) if entry else _find_entry(project_root)
    if not entry_path or not Path(entry_path).is_file():
        raise FileNotFoundError(
            f"no Remotion entry in {project_root}; for HyperFrames projects call "
            "hyperframes_compose with snapshots=true instead"
        )
    comp_id = composition
    if not comp_id:
        found = _list_compositions(Path(entry_path))
        if not found:
            raise RuntimeError("remotion compositions returned no composition id")
        comp_id = found[0]

    wanted = [int(f) for f in (frames or [0])][:8]
    out_dir = project_root / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
    images: list[str] = []
    for frame in wanted:
        target = out_dir / f"frame-{frame:04d}.png"
        cmd = [npx, "remotion", "still", str(entry_path), comp_id, str(target),
               f"--frame={frame}", "--log=error"]
        public_dir = project_root / "public"
        if public_dir.is_dir():
            cmd += ["--public-dir", str(public_dir)]
        proc = subprocess.run(cmd, cwd=str(_COMPOSER_DIR), capture_output=True, text=True,
                              timeout=180, env=_node_env())
        if proc.returncode == 0 and target.is_file():
            images.append(str(target))
    if not images:
        return {"rendered": False, "error": "no stills produced (check composition id / entry)"}

    sheet = _contact_sheet(images, out_dir / "sheet.png", width)
    return {
        "rendered": True,
        "composition": comp_id,
        "frames": wanted[: len(images)],
        "images": images,
        "contact_sheet": str(sheet) if sheet else None,
        "hint": "Show these to the user (om_gate(previews=[...])) before a full render.",
    }


def _contact_sheet(images: list[str], target: Path, width: int = 480) -> Path | None:
    """2-3 columns grid so the UI can show every still at once."""
    try:
        from PIL import Image

        thumbs = []
        for path in images:
            try:
                img = Image.open(path).convert("RGB")
            except Exception:
                continue
            ratio = width / max(1, img.width)
            thumbs.append(img.resize((width, max(1, int(img.height * ratio)))))
        if not thumbs:
            return None
        cols = 3 if len(thumbs) >= 3 else len(thumbs)
        rows = (len(thumbs) + cols - 1) // cols
        row_h = max(t.height for t in thumbs)
        sheet = Image.new("RGB", (cols * width, rows * row_h), (11, 12, 16))
        for index, thumb in enumerate(thumbs):
            x = (index % cols) * width
            y = (index // cols) * row_h
            sheet.paste(thumb, (x, y))
        sheet.save(target, "PNG")
        return target
    except Exception:
        return None


def om_quote(
    project_id: str,
    shots: list[dict[str, Any]] | None = None,
    render: dict[str, Any] | None = None,
    headline: str = "",
    wait: bool = True,
    timeout_seconds: int = 900,
    brief: str = "",
    duration_seconds: float = 0,
    aspect: str = "9:16",
    with_voice: bool = False,
) -> dict[str, Any]:
    """Price a plan before spending, and (optionally) block for approval.

    Two shapes are accepted: an explicit shot list, or a one-line brief with a
    duration (so the very first reply can already carry a number).
    """
    from adplus import agent_bridge
    from adplus.quote import build_quote, describe, plan_from_brief

    if not (PROJECTS_DIR / project_id).is_dir():
        raise FileNotFoundError(f"no project at {PROJECTS_DIR / project_id}")

    assumptions: list[str] = []
    if not shots:
        if not (brief or duration_seconds):
            raise ValueError("pass either `shots`, or `brief` + `duration_seconds`")
        shots, derived_render, assumptions = plan_from_brief(
            brief, duration_seconds or 15, aspect, with_voice
        )
        render = render or derived_render
    quote = build_quote(project_id, shots or [], render or None, headline)
    quote["assumptions"] = assumptions
    quote["id"] = agent_bridge.new_id("q")
    quote["status"] = "pending"
    agent_bridge.write_record("quotes", project_id, quote)

    result: dict[str, Any] = {
        "quote_id": quote["id"],
        "summary": describe(quote),
        "total_usd": quote["total_usd"],
        "range_usd": [quote["low_usd"], quote["high_usd"]],
        "eta_seconds": quote["eta_seconds"],
        "pending_quotes": quote["pending_quotes"],
        "line_items": quote["line_items"],
        "assumptions": assumptions,
        "approved": None,
    }
    if not wait:
        return result

    final = agent_bridge.wait_for_decision("quotes", project_id, quote["id"], timeout_seconds)
    result["approved"] = final.get("status") == "approved"
    result["status"] = final.get("status")
    result["comment"] = (final.get("decision") or {}).get("comment", "")
    if not result["approved"]:
        result["hint"] = (
            "The user did not approve. Ask what to change, adjust the plan, then quote again."
            if final.get("status") != "timeout"
            else "Nobody answered in time. Summarise the plan and wait for the next instruction."
        )
    return result


def om_proposal(
    project_id: str,
    packet: dict[str, Any],
    headline: str = "",
    brief: str = "",
    duration_seconds: float = 0,
    aspect: str = "9:16",
    with_voice: bool = False,
) -> dict[str, Any]:
    """Write an Ad+ proposal packet and create a non-blocking quote in one call.

    This is the plan-page path. It deliberately skips the cinematic pipeline's
    research/gate prerequisites: the user is buying a proposal, not advancing
    a render pipeline yet.
    """
    project_root = PROJECTS_DIR / project_id
    if not project_root.is_dir():
        raise FileNotFoundError(f"no project at {project_root}")
    if not isinstance(packet, dict) or not packet:
        raise ValueError("packet must be a non-empty object")
    concept = packet.get("concept") if isinstance(packet.get("concept"), dict) else {}
    title = str(headline or concept.get("title") or "方案")
    duration = float(duration_seconds or 0)
    if not duration:
        try:
            project = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
            duration = float(project.get("duration_s") or 15)
        except Exception:
            duration = 15.0
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    packet = {**packet, "generated_at": packet.get("generated_at") or now}
    target = project_root / "artifacts" / "proposal_packet.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    quote = om_quote(
        project_id,
        brief=brief or str(concept.get("hook") or title),
        duration_seconds=duration,
        aspect=aspect,
        wait=False,
        headline=title,
        with_voice=with_voice,
    )
    try:
        from adplus import project_store
        project = project_store.load_project(project_id)
        if project and project.get("status") in ("draft", "briefing", "quoted"):
            project_store.update_project(project_id, {"status": "quoted"})
    except Exception:
        pass
    return {
        "proposal_path": str(target),
        "quote": quote,
        "packet": packet,
    }


def om_gate(
    project_id: str,
    stage: str,
    note: str = "",
    artifacts: list[str] | None = None,
    previews: list[str] | None = None,
    wait: bool = True,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Pause at a stage boundary and wait for a human decision."""
    from adplus import agent_bridge

    if not (PROJECTS_DIR / project_id).is_dir():
        raise FileNotFoundError(f"no project at {PROJECTS_DIR / project_id}")
    record = {
        "id": agent_bridge.new_id("a"),
        "project_id": project_id,
        "stage": stage,
        "status": "pending",
        "note": note,
        "artifacts": artifacts or [],
        "previews": previews or [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    agent_bridge.write_record("approvals", project_id, record)
    result: dict[str, Any] = {"gate_id": record["id"], "stage": stage, "approved": None}
    if not wait:
        return result
    final = agent_bridge.wait_for_decision("approvals", project_id, record["id"], timeout_seconds)
    result["approved"] = final.get("status") == "approved"
    result["status"] = final.get("status")
    result["comment"] = (final.get("decision") or {}).get("comment", "")
    if not result["approved"]:
        result["hint"] = (
            "Rejected: rework this stage using the comment, then call om_gate again."
            if final.get("status") != "timeout"
            else "No answer in time: stop here and ask the user how to proceed."
        )
    return result


# --------------------------------------------------------------------------- #
# MCP surface
# --------------------------------------------------------------------------- #

_LONG_RUNNING = {
    "image_selector",
    "video_selector",
    "tts_selector",
    "video_compose",
    "music_selector",
}


def _facade() -> list[types.Tool]:
    obj = {"type": "object", "additionalProperties": False}
    return [
        types.Tool(
            name="om_capabilities",
            description=(
                "Report which media capabilities are configured right now (image, video, TTS, "
                "music, composition runtimes) and what a missing key would unlock. Call this "
                "first: it decides which production path is honest for the current setup."
            ),
            inputSchema={**obj, "properties": {}},
        ),
        types.Tool(
            name="om_list_tools",
            description=(
                "List registry tools, optionally filtered by capability or name substring. Use it "
                "to find the concrete provider tool behind a facade call or to check pricing hints "
                "before a paid run."
            ),
            inputSchema={
                **obj,
                "properties": {
                    "capability": {"type": "string", "description": "e.g. video_generation, tts, image_generation"},
                    "query": {"type": "string", "description": "substring matched against tool name and provider"},
                },
            },
        ),
        types.Tool(
            name="om_start_project",
            description=(
                "Create the canonical project workspace (artifacts/, assets/, renders/) and the "
                "project.json marker the Backlot board reads. Every production starts here."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id", "title"],
                "properties": {
                    "project_id": {"type": "string", "description": "kebab-case, also the directory name"},
                    "title": {"type": "string"},
                    "pipeline": {"type": "string", "default": "cinematic"},
                },
            },
        ),
        types.Tool(
            name="om_checkpoint",
            description=(
                "Read a project's pipeline state: completed stages, the next stage to run, and the "
                "latest checkpoint. Use it to resume instead of restarting."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "pipeline": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="om_write_checkpoint",
            description=(
                "Persist a stage checkpoint so the pipeline can advance. Call it after each stage "
                "with that stage's canonical artifact. `status` completed requires the canonical "
                "artifact for the stage; gated stages additionally require human_approved=true. "
                "This is the only supported way to advance a project — do not write checkpoint "
                "files by hand."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id", "stage"],
                "properties": {
                    "project_id": {"type": "string"},
                    "stage": {
                        "type": "string",
                        "enum": [
                            "research",
                            "proposal",
                            "script",
                            "scene_plan",
                            "assets",
                            "edit",
                            "compose",
                            "publish",
                        ],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["completed", "awaiting_human", "in_progress", "failed"],
                        "default": "completed",
                    },
                    "artifacts": {
                        "type": "object",
                        "description": "Canonical artifact keyed by artifact name, e.g. {\"script\": {...}}",
                    },
                    "pipeline": {"type": "string", "description": "pipeline_type, backfilled from project.json when omitted"},
                    "human_approved": {"type": "boolean", "default": False},
                    "review": {"type": "object"},
                    "cost_snapshot": {"type": "object"},
                    "metadata": {"type": "object"},
                    "error": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="om_artifacts",
            description="List the files a project has produced so far (relative paths + sizes).",
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id"],
                "properties": {"project_id": {"type": "string"}},
            },
        ),
        types.Tool(
            name="om_render",
            description=(
                "Render a hand-authored Remotion composition that lives in the project folder "
                "(atelier mode: index.tsx + Composition.tsx). Use this instead of shelling out to "
                "npx remotion yourself: it runs from the repo's composer, enforces a wall-clock "
                "budget, and verifies the output file before reporting success."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "composition": {"type": "string", "description": "composition id; auto-detected when omitted"},
                    "entry": {"type": "string", "description": "entry file relative to the project; auto-detected when omitted"},
                    "output": {"type": "string", "description": "absolute output path; defaults to renders/<project>-<composition>.mp4"},
                    "timeout_seconds": {"type": "integer", "default": 600},
                },
            },
        ),
        types.Tool(
            name="om_call_tool",
            description=(
                "Run one registry tool synchronously and return its data, artifacts and cost. Use "
                "it for fast tools only (probes, validation, trimming). Anything that generates "
                "media belongs in om_submit."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "params"],
                "properties": {
                    "tool": {"type": "string", "description": "registry tool name, e.g. video_trimmer"},
                    "params": {"type": "object", "description": "that tool's input schema"},
                },
            },
        ),
        types.Tool(
            name="om_submit",
            description=(
                "Start a slow tool in the background and return a job id. Use for anything that "
                "generates or renders media: image_selector, video_selector, tts_selector, "
                "video_compose. Poll with om_job."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "params"],
                "properties": {
                    "tool": {"type": "string"},
                    "params": {"type": "object"},
                },
            },
        ),
        types.Tool(
            name="om_job",
            description="Check a submitted job: status, elapsed seconds, result or error.",
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["job_id"],
                "properties": {"job_id": {"type": "string"}},
            },
        ),
        types.Tool(
            name="om_quote",
            description=(
                "Price a plan before spending money. Pass either an explicit shot list "
                "([{tool, label?, params?, count?}]) or just `brief` + `duration_seconds` — the "
                "latter derives a default shot plan so you can quote in the first reply. Returns "
                "a dollar range, ETA and the assumptions behind them, and blocks until the user "
                "approves or rejects (wait=false skips the wait). Quote before any generation."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "headline": {"type": "string"},
                    "wait": {"type": "boolean", "default": True},
                    "timeout_seconds": {"type": "integer", "default": 900},
                    "brief": {"type": "string", "description": "One-line brief when the shot list is not known yet."},
                    "duration_seconds": {"type": "number", "description": "Target duration, e.g. 15."},
                    "aspect": {"type": "string", "default": "9:16"},
                    "with_voice": {"type": "boolean", "default": False},
                    "render": {
                        "type": "object",
                        "properties": {
                            "frames": {"type": "integer"},
                            "fps": {"type": "number"},
                            "seconds_per_frame": {"type": "number"},
                        },
                    },
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["tool"],
                            "properties": {
                                "tool": {"type": "string"},
                                "label": {"type": "string"},
                                "count": {"type": "integer"},
                                "params": {"type": "object"},
                            },
                        },
                    },
                },
            },
        ),
        types.Tool(
            name="om_preview",
            description=(
                "Render a few still frames from the project's Remotion composition so the user "
                "can approve the look before a full render (seconds, not minutes). Returns image "
                "paths plus a contact sheet."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "frames": {"type": "array", "items": {"type": "integer"}},
                    "composition": {"type": "string"},
                    "entry": {"type": "string"},
                    "width": {"type": "integer", "default": 480},
                },
            },
        ),
        types.Tool(
            name="om_proposal",
            description=(
                "Ad+ plan-page tool: write a proposal packet (concept, script, shots, deliverables, "
                "assumptions, exclusions) and create a pending quote in one non-blocking call. "
                "Use this instead of om_write_checkpoint + om_quote for the proposal stage."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id", "packet"],
                "properties": {
                    "project_id": {"type": "string"},
                    "packet": {"type": "object", "description": "proposal_packet JSON"},
                    "headline": {"type": "string"},
                    "brief": {"type": "string"},
                    "duration_seconds": {"type": "number"},
                    "aspect": {"type": "string"},
                    "with_voice": {"type": "boolean"},
                },
            },
        ),
        types.Tool(
            name="om_gate",
            description=(
                "Pause at a stage boundary for a human decision. Blocks until the user approves "
                "or rejects; a rejection returns their comment so you can rework the stage. Use "
                "it at scene_plan and before the final render."
            ),
            inputSchema={
                "type": "object",
                "additionalProperties": False,
                "required": ["project_id", "stage"],
                "properties": {
                    "project_id": {"type": "string"},
                    "stage": {"type": "string"},
                    "note": {"type": "string"},
                    "wait": {"type": "boolean", "default": True},
                    "timeout_seconds": {"type": "integer", "default": 900},
                    "artifacts": {"type": "array", "items": {"type": "string"}},
                    "previews": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        types.Tool(
            name="om_reload_env",
            description="Reload provider keys from the secrets file into this process (after a settings change).",
            inputSchema={**obj, "properties": {}},
        ),
    ]


_DISPATCH = {
    "om_capabilities": om_capabilities,
    "om_list_tools": om_list_tools,
    "om_start_project": om_start_project,
    "om_checkpoint": om_checkpoint,
    "om_artifacts": om_artifacts,
    "om_write_checkpoint": om_write_checkpoint,
    "om_reload_env": om_reload_env,
    "om_render": om_render,
    "om_preview": om_preview,
    "om_proposal": om_proposal,
    "om_quote": om_quote,
    "om_gate": om_gate,
}


def build_server() -> Server:
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)

    async def handle_list_tools(ctx: Any, params: types.PaginatedRequestParams) -> types.ListToolsResult:
        return types.ListToolsResult(tools=_facade())

    async def handle_call_tool(ctx: Any, call: types.CallToolRequestParams) -> types.CallToolResult:
        name = call.name
        args = dict(call.arguments or {})
        try:
            if name in _DISPATCH:
                return _text(_DISPATCH[name](**args))
            if name == "om_call_tool":
                return _text(_tool_result(args["tool"], args.get("params") or {}))
            if name == "om_submit":
                job_id = _start_job(args["tool"], args.get("params") or {})
                return _text({"job_id": job_id, "tool": args["tool"], "poll_with": "om_job"})
            if name == "om_job":
                return _text(_job_view(args["job_id"]))
            return _error(f"unknown tool {name!r}")
        except KeyError as exc:
            return _error(str(exc))
        except TypeError as exc:
            return _error(f"bad arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - the model needs the message, not a traceback
            return _error(f"{type(exc).__name__}: {exc}")

    server.add_request_handler("tools/list", types.PaginatedRequestParams, handle_list_tools)
    server.add_request_handler("tools/call", types.CallToolRequestParams, handle_call_tool)
    return server


async def _serve() -> None:
    applied = load_secrets()
    _registry_or_raise()  # import once, up front: discovery is slow
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    import asyncio

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
