"""gateway.py — single Hermes gateway lifecycle helper.

Per ADR-0008 §Amendment-2026-06-08 + ROADMAP A11 [REVISED]: agentdex-cli drives
ONE long-lived `hermes gateway --profile agentdex` subprocess per expedition.
This module provides spawn-once + health-check + shutdown helpers.

PID-file discovery mirrors `hermes_cli/gateway.py:309 _scan_gateway_pids` model:
PID lives at `<HERMES_HOME>/profiles/<profile>/gateway.pid`.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def _profile_dir(profile: str) -> Path:
    return _hermes_home() / "profiles" / profile


def _pid_file(profile: str) -> Path:
    return _profile_dir(profile) / "gateway.pid"


def _read_pid(profile: str) -> int | None:
    pf = _pid_file(profile)
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


@dataclass
class GatewayHandle:
    """Handle to a running (or to-be-spawned) hermes gateway."""

    pid: int
    profile: str
    base_url: str
    popen: subprocess.Popen | None = None  # None = pre-existing, do not shutdown
    extras: dict[str, Any] = field(default_factory=dict)

    def shutdown(self) -> bool:
        """Shutdown the gateway IF this handle spawned it.

        Returns True if a process was terminated; False if handle owns no process.
        Pre-existing gateways (popen=None) are intentionally left running.
        """
        if self.popen is None:
            return False
        try:
            self.popen.terminate()
            self.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.popen.kill()
            self.popen.wait()
        except (OSError, ProcessLookupError):
            pass
        return True

    def post_turn(
        self,
        prompt: str,
        tool_args: dict[str, Any] | None = None,
        *,
        trace_context: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """HTTP POST a turn to the gateway.

        trace_context: optional dict of HTTP headers (e.g. from
        agentdex_observe.get_trace_context_headers()) for cross-process Langfuse
        trace propagation per R3 spike (phase-4 spec).

        M2 stub: returns the request envelope as a dict so downstream tests can
        verify trace_context is forwarded. The actual HTTP call lands at M5.
        """
        envelope = {
            "prompt": prompt,
            "tool_args": tool_args or {},
            "headers": dict(trace_context or {}),
            "base_url": self.base_url,
        }
        return envelope


def discover_gateway(profile: str = "agentdex") -> GatewayHandle | None:
    """Find an already-running gateway for `profile` via its PID file.

    Returns a GatewayHandle (popen=None) if alive; None if no PID file or stale.
    """
    pid = _read_pid(profile)
    if pid is None or not _pid_alive(pid):
        return None
    return GatewayHandle(
        pid=pid,
        profile=profile,
        base_url=f"http://localhost:{_default_port(profile)}",
        popen=None,
        extras={"discovered": True},
    )


def _default_port(profile: str) -> int:
    """Default gateway port. Hermes 0.15.1 typically uses 8742; allow env override."""
    return int(os.environ.get("HERMES_GATEWAY_PORT", "8742"))


def ensure_gateway(
    profile: str = "agentdex",
    port: int | None = None,
    timeout: float = 30.0,
    spawn_cmd: list[str] | None = None,
) -> GatewayHandle:
    """Ensure a gateway is running for `profile`. Spawn if absent.

    Idempotent. If discovery finds a live gateway, returns that handle. Otherwise
    spawns `hermes gateway --profile <profile>` and polls for liveness up to
    `timeout` seconds.

    spawn_cmd override: tests pass a no-op or fake binary to avoid spawning real
    Hermes.
    """
    existing = discover_gateway(profile)
    if existing is not None:
        return existing

    cmd = spawn_cmd or ["hermes", "gateway", "--profile", profile]
    profile_dir = _profile_dir(profile)
    profile_dir.mkdir(parents=True, exist_ok=True)

    popen = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        pid = _read_pid(profile)
        if pid is not None and _pid_alive(pid):
            return GatewayHandle(
                pid=pid,
                profile=profile,
                base_url=f"http://localhost:{port or _default_port(profile)}",
                popen=popen,
                extras={"spawned": True},
            )
        if popen.poll() is not None:
            raise RuntimeError(
                f"hermes gateway --profile {profile} exited with code {popen.returncode} during startup"
            )
        time.sleep(0.2)

    popen.terminate()
    raise TimeoutError(
        f"hermes gateway --profile {profile} did not write PID within {timeout}s; check HERMES_HOME={_hermes_home()}"
    )


__all__ = ["GatewayHandle", "discover_gateway", "ensure_gateway"]
