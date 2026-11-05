"""Drive Pi 1.x over its RPC protocol (JSONL on stdio).

One bridge per chat session. The process is long-lived: prompts are sent as
commands, and everything Pi emits (assistant text, tool calls, run state) is
queued for the WebSocket to forward to the UI.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from app import env_utils, secrets_store


def pi_executable() -> str | None:
    return env_utils.find_node_tool("pi")


class PiBridge:
    def __init__(
        self,
        cwd: str | Path,
        provider: str | None = None,
        model: str | None = None,
        session_dir: str | Path | None = None,
        session_id: str | None = None,
        resume_path: str | Path | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        exe = pi_executable()
        if not exe:
            raise RuntimeError("pi executable not found (install Pi, or add ~/.local/bin to PATH)")
        hints = Path(__file__).resolve().parent / "agent-hints.md"
        args = [exe, "--mode", "rpc", "--approve"]
        if hints.is_file():
            args += ["--append-system-prompt", str(hints)]
        if session_dir:
            Path(session_dir).mkdir(parents=True, exist_ok=True)
            args += ["--session-dir", str(session_dir)]
        if resume_path:
            args += ["--session", str(resume_path)]
        elif session_id:
            args += ["--session-id", session_id]
        else:
            args += ["--no-session"]
        if provider and model:
            args += ["--provider", provider, "--model", model]
        if extra_args:
            args += extra_args
        env = env_utils.spawn_env(secrets_store.merged_env())
        self.proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self.events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._running = False
        self._closed = False
        self._pending_usage: dict[str, Any] | None = None
        self.totals: dict[str, float] = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
                                         "totalTokens": 0, "cost": 0.0}
        try:
            self.budget_usd = float(os.environ.get("OPENMONTAGE_SESSION_BUDGET_USD", "2.0"))
        except ValueError:
            self.budget_usd = 2.0
        self._budget_tripped = False
        threading.Thread(target=self._read_stdout, name="pi-rpc-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="pi-rpc-err", daemon=True).start()

    # ---- io ------------------------------------------------------------- #

    def _mark_activity(self, record: dict[str, Any]) -> None:
        if record.get("type") == "agent_settled":
            self._running = False
        elif record.get("type") in ("message_start", "tool_execution_start", "prompt_accepted"):
            self._running = True

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                self.events.put({"type": "log", "raw": line})
                continue
            self._track_usage(record)
            self._mark_activity(record)
            self.events.put(record)
        self.events.put(None)

    def _track_usage(self, record: dict[str, Any]) -> None:
        """Accumulate provider-reported token usage and cost per assistant turn."""
        kind = record.get("type")
        if kind == "message_update" and isinstance(record.get("usage"), dict):
            self._pending_usage = record["usage"]
        elif kind in {"message_end", "turn_end"} and self._pending_usage:
            usage = self._pending_usage
            self._pending_usage = None
            cost = usage.get("cost") or {}
            self.totals["input"] += usage.get("input", 0) or 0
            self.totals["output"] += usage.get("output", 0) or 0
            self.totals["cacheRead"] += usage.get("cacheRead", 0) or 0
            self.totals["cacheWrite"] += usage.get("cacheWrite", 0) or 0
            self.totals["totalTokens"] += usage.get("totalTokens", 0) or 0
            self.totals["cost"] += float(cost.get("total") or 0)
            self.events.put({"type": "usage", "totals": dict(self.totals), "last": usage,
                             "budget_usd": self.budget_usd})
            if not self._budget_tripped and self.totals["cost"] >= self.budget_usd:
                self._budget_tripped = True
                self.events.put({
                    "type": "budget_exceeded",
                    "cost": round(self.totals["cost"], 4),
                    "budget_usd": self.budget_usd,
                })
                try:
                    self.abort()
                except Exception:
                    pass

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            text = line.strip()
            if text:
                self.events.put({"type": "log", "raw": text})

    def alive(self) -> bool:
        return not self._closed and self.proc.poll() is None

    @property
    def running(self) -> bool:
        return self._running

    def send(self, record: dict[str, Any]) -> None:
        if self._closed or self.proc.poll() is not None:
            raise RuntimeError("pi session is not running")
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    # ---- commands ------------------------------------------------------- #

    def prompt(self, text: str) -> str:
        request_id = uuid.uuid4().hex[:8]
        self._running = True
        self.send({"id": request_id, "type": "prompt", "message": text})
        return request_id

    def abort(self) -> None:
        self.send({"id": uuid.uuid4().hex[:8], "type": "abort"})

    def get_messages(self) -> str:
        request_id = uuid.uuid4().hex[:8]
        self.send({"id": request_id, "type": "get_messages"})
        return request_id

    def get_state(self) -> str:
        request_id = uuid.uuid4().hex[:8]
        self.send({"id": request_id, "type": "get_state"})
        return request_id

    def close(self) -> None:
        self._closed = True
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
