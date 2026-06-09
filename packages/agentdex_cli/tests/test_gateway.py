"""test_gateway — Phase 4 gateway helper acceptance tests.

Three tests per phase-4.md spec:
(a) discover_gateway returns None when no PID file
(b) ensure_gateway spawns + cleans up (use tmp_path HERMES_HOME)
(c) GatewayHandle.shutdown no-ops on pre-existing process (popen=None)
"""

from __future__ import annotations

import os

import pytest
from agentdex_cli.orchestrator.gateway import (
    GatewayHandle,
    discover_gateway,
    ensure_gateway,
)


@pytest.fixture
def isolated_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    yield tmp_path


def test_discover_gateway_returns_none_when_no_pid_file(isolated_hermes_home):
    assert discover_gateway("agentdex") is None


def test_ensure_gateway_spawns_and_cleans_up(isolated_hermes_home, monkeypatch):
    """Use a no-op spawn_cmd that writes the PID file the helper expects."""
    profile_dir = isolated_hermes_home / "profiles" / "agentdex"
    profile_dir.mkdir(parents=True, exist_ok=True)
    pid_file = profile_dir / "gateway.pid"

    # fake binary: a python -c that writes the pid file then sleeps
    spawn_cmd = [
        "python3",
        "-c",
        f"import os, time; open('{pid_file}', 'w').write(str(os.getpid())); time.sleep(60)",
    ]

    handle = ensure_gateway(profile="agentdex", timeout=5.0, spawn_cmd=spawn_cmd)
    assert handle.pid > 0
    assert handle.popen is not None  # we spawned it
    assert handle.profile == "agentdex"

    # cleanup
    assert handle.shutdown() is True


def test_gateway_handle_shutdown_noops_on_preexisting():
    """A handle with popen=None (discovered, not spawned) does not kill anything."""
    handle = GatewayHandle(
        pid=os.getpid(),
        profile="agentdex",
        base_url="http://localhost:8742",
        popen=None,
    )
    assert handle.shutdown() is False
