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
from adx_showdown.sidecar import Sidecar, SidecarError
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
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


class _FailingSidecar:
    """A sidecar whose lazy start() always raises — e.g. node_modules/sidecar.mjs
    missing on the deploy. returncode stays None (it never spawned a process)."""

    returncode = None

    async def start(self) -> None:
        raise SidecarError("sidecar.mjs missing (simulated)")


def _battle_token(authority: ConsentAuthority) -> str:
    pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    claims = ConsentClaims(
        token_id="t" + "0" * 16,
        owner="eddie@oppie.xyz",
        agent_name="PolarBot",
        agent_pubkey_hex=pub,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=0.0,
        expires_at=9_999_999_999.0,  # far future — clock-independent
        confirmed_via="test",
    )
    return authority.mint(claims)


def test_healthz_503_after_failed_lazy_start(tmp_path: Path):
    """A lazy sidecar start() that raises must flip /healthz to 503.

    The old code stored the unstarted instance (returncode None → reads as alive),
    so /healthz returned 200 while every sim request failed 'sidecar not started'
    and the platform never recycled the container (PR #238 review).
    """
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    app = create_app(gateway, sidecar_factory=_FailingSidecar)
    with TestClient(app, raise_server_exceptions=False) as c:
        # Ready before any battle (sidecar lazy, not yet started).
        assert c.get("/healthz").status_code == 200
        # A request that triggers the lazy start, which fails.
        r = c.post("/team/draft", json={"token": _battle_token(authority), "export": "Pikachu"})
        assert r.status_code >= 400  # start failed → opaque error, not a hang
        # The failed lazy start is now visible to the platform.
        assert c.get("/healthz").status_code == 503
        # The broken, unstarted instance was NOT stored (next request retries fresh).
        assert app.state.sidecar is None


def test_healthz_recovers_to_200_when_start_flag_cleared(client):
    """The sticky failure flag is the only thing forcing 503 once set; a later
    successful start (flag back to False) returns the probe to ready."""
    c, app = client
    app.state.sidecar_start_failed = True
    assert c.get("/healthz").status_code == 503
    app.state.sidecar_start_failed = False
    assert c.get("/healthz").status_code == 200
