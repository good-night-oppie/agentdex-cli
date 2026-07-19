"""Out-of-process battle policy for an ``AgentCandidate.entrypoint``."""

from __future__ import annotations

import json
import os
import select
import shlex
import signal
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from adx_showdown.selfplay.agent import Agent


class EntrypointAgent(Agent):
    """Persistent JSONL client; backend faults abstain instead of crashing play."""

    name = "entrypoint"

    def __init__(self, entrypoint: str, *, cwd: Path, timeout_sec: float = 30.0) -> None:
        argv = shlex.split(entrypoint)
        if not argv:
            raise ValueError("candidate entrypoint is empty after shlex.split")
        self._timeout_sec = timeout_sec
        self._proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def decide(self, harness: Any, ctx: Mapping[str, Any]) -> str | None:
        proc = self._proc
        if proc.poll() is not None or proc.stdin is None or proc.stdout is None:
            return None
        try:
            payload = {"type": "observation", "battle": dict(ctx)}
            proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            proc.stdin.flush()
            ready, _, _ = select.select([proc.stdout], [], [], self._timeout_sec)
            if not ready:
                self.close()
                return None
            reply = json.loads(proc.stdout.readline())
            if reply.get("type") != "action":
                return None
            action = reply.get("action")
            return str(action) if action is not None else None
        except (BrokenPipeError, OSError, TypeError, ValueError, json.JSONDecodeError):
            self.close()
            return None

    def close(self) -> None:
        proc = self._proc
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        except ProcessLookupError:
            pass

    def __enter__(self) -> EntrypointAgent:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
