"""/healthz is a real readiness probe, not a static {ok:true} (OPS-P1-healthz-readiness).

Once the sim tier (Sidecar or SidecarPool) has spawned, a crashed node process must
surface as 503 so the platform recycles the container instead of serving an
OOM/dead-sidecar spiral. Before first battle (sidecar None) the gateway is ready.
Liveness is read from the cached returncode — no IPC — so the probe never hangs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from adx_showdown.pool import SidecarPool
from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
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
        yield c, app


class _FakeSidecar:
    """Stands in for a single Sidecar — only `.returncode` is read by /healthz."""

    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode


def test_healthz_ready_before_sidecar_spawned(client):
    c, app = client
    app.state.sidecar = None  # lazy: not spawned until first battle
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_healthz_ok_when_sidecar_alive(client):
    c, app = client
    app.state.sidecar = _FakeSidecar(returncode=None)  # running
    try:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        app.state.sidecar = None  # so lifespan shutdown does not stop() the fake


def test_healthz_503_when_sidecar_crashed(client):
    c, app = client
    app.state.sidecar = _FakeSidecar(returncode=1)  # node process exited
    try:
        r = c.get("/healthz")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert "sidecar" in body["detail"]
    finally:
        app.state.sidecar = None


def test_healthz_503_when_a_pool_member_is_dead(client):
    c, app = client
    pool = SidecarPool(size=2)  # not started — members report returncode None
    pool._sidecars[1]._last_returncode = 137  # simulate one member's OOM-kill
    app.state.sidecar = pool
    try:
        r = c.get("/healthz")
        assert r.status_code == 503
        assert r.json()["ok"] is False
    finally:
        app.state.sidecar = None


def test_pool_any_dead_unit():
    pool = SidecarPool(size=2)
    assert pool.any_dead() is False  # fresh pool, nothing has exited
    pool._sidecars[0]._last_returncode = 0  # a clean-exited member still counts as not-running
    assert pool.any_dead() is True
