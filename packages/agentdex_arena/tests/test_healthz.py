"""/healthz is a real readiness probe, not a static {ok:true} (OPS-P1-healthz-readiness).

Once the sim tier (Sidecar or SidecarPool) has spawned, a crashed node process must
surface as 503 so the platform recycles the container instead of serving an
OOM/dead-sidecar spiral. Before first battle (sidecar None) the gateway is ready.
Liveness is read from the cached returncode — no IPC — so the probe never hangs.
"""

from __future__ import annotations

import asyncio
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


def _make_gateway(tmp_path: Path) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


def test_lazy_sidecar_start_is_serialized(tmp_path: Path):
    """Two concurrent first requests must spawn EXACTLY ONE sidecar — without the
    lock both observe app.state.sidecar is None and start two Node processes that
    monopolize the shared pool (PR #248 review)."""
    gateway = _make_gateway(tmp_path)
    factory_calls: list[int] = []

    class _SlowStart:
        returncode = None

        async def start(self) -> None:
            await asyncio.sleep(0.01)  # yield so a second caller can race in

        async def stop(self) -> None:
            pass

    def factory() -> _SlowStart:
        factory_calls.append(1)
        return _SlowStart()

    app = create_app(gateway, sidecar_factory=factory)

    async def _run() -> None:
        a, b = await asyncio.gather(app.state.ensure_sidecar(), app.state.ensure_sidecar())
        assert a is b  # both callers share the single started instance

    asyncio.run(_run())
    assert len(factory_calls) == 1


def test_failed_lazy_start_stops_partial_sidecar(tmp_path: Path):
    """A start() that raised after spawning a child must be stopped, not leaked
    (PR #248 review)."""
    gateway = _make_gateway(tmp_path)
    stopped: list[int] = []

    class _PartialStart:
        returncode = None

        async def start(self) -> None:
            raise SidecarError("ready-event timeout after spawn")

        async def stop(self) -> None:
            stopped.append(1)

    app = create_app(gateway, sidecar_factory=_PartialStart)

    async def _run() -> None:
        with pytest.raises(SidecarError):
            await app.state.ensure_sidecar()

    asyncio.run(_run())
    assert stopped == [1]  # the partially-started child was torn down
    assert app.state.sidecar is None
    assert app.state.sidecar_start_failed is True


def test_partial_start_cleanup_completes_even_when_cancelled(tmp_path: Path):
    """If the lazy-start cleanup is itself cancelled (client disconnect / shutdown
    during ready-timeout teardown), the partially-spawned child must STILL be fully
    stopped — the stop() is shielded from the cancellation (PR #258 review)."""
    gateway = _make_gateway(tmp_path)
    stopped: list[int] = []
    stop_started = asyncio.Event()

    class _PartialStartSlowStop:
        returncode = None

        async def start(self) -> None:
            raise SidecarError("ready-event timeout after spawn")

        async def stop(self) -> None:
            stop_started.set()
            await asyncio.sleep(0.02)  # teardown takes time
            stopped.append(1)

    app = create_app(gateway, sidecar_factory=_PartialStartSlowStop)

    async def _run() -> None:
        t = asyncio.create_task(app.state.ensure_sidecar())
        await stop_started.wait()  # we're now inside the stop()
        t.cancel()  # cancel the request mid-cleanup
        with pytest.raises((asyncio.CancelledError, SidecarError)):
            await t
        # The cleanup AWAITS the teardown to completion before propagating the cancel,
        # so the child is already reaped by the time the cancel surfaces — no trailing
        # sleep needed (shield-without-drain would leave stopped == [] here).
        assert stopped == [1]
        assert app.state.sidecar_start_failed is True

    asyncio.run(_run())
