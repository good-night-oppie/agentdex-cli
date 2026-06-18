"""/metrics exposes operator-visible launch counters (OPS-P1-metrics-stats).

Before this there were zero metrics — the gap between a healthy spike and an OOM
spiral was invisible. /metrics surfaces active battles, registered agents, the
capacity-shed (503) counter, and best-effort sidecar RSS (bounded so a wedged
sidecar can't hang the probe).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


@pytest.fixture()
def ctx(tmp_path: Path):
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, app, gateway


def test_metrics_empty_state(ctx):
    c, _app, _gw = ctx
    body = c.get("/metrics").json()
    assert body["active_battles"] == 0
    assert body["registered_agents"] == 0
    assert body["cap_503_total"] == 0
    assert body["sidecar_spawned"] is False
    assert body["sidecar_pool_size"] == 0
    assert body["sidecar_rss_mb"] is None


def test_metrics_counts_sessions_and_registered(ctx):
    c, _app, gw = ctx
    gw.sessions["battle-x"] = object()  # type: ignore[assignment]
    gw.sessions["battle-y"] = object()  # type: ignore[assignment]
    gw._registered.add("agent-a")
    body = c.get("/metrics").json()
    assert body["active_battles"] == 2
    assert body["registered_agents"] == 1


def test_metrics_surfaces_cap_503_counter(ctx):
    c, _app, gw = ctx
    gw.cap_503_total = 3
    assert c.get("/metrics").json()["cap_503_total"] == 3


class _FakeSidecar:
    returncode = None

    def __init__(self, rss: float | None = None, raises: bool = False) -> None:
        self._rss = rss
        self._raises = raises

    async def rss_mb(self) -> float:
        if self._raises:
            raise RuntimeError("sidecar wedged")
        assert self._rss is not None
        return self._rss


def test_metrics_reports_sidecar_rss(ctx):
    c, app, _gw = ctx
    app.state.sidecar = _FakeSidecar(rss=42.5)
    try:
        body = c.get("/metrics").json()
        assert body["sidecar_spawned"] is True
        assert body["sidecar_rss_mb"] == 42.5
    finally:
        app.state.sidecar = None


def test_metrics_rss_none_when_sidecar_errors(ctx):
    c, app, _gw = ctx
    app.state.sidecar = _FakeSidecar(raises=True)  # alive but unresponsive
    try:
        body = c.get("/metrics").json()
        assert body["sidecar_spawned"] is True
        assert body["sidecar_rss_mb"] is None  # diagnostic best-effort, never hangs/fails
    finally:
        app.state.sidecar = None
