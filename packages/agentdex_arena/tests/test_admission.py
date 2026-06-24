"""Admission control: per-owner concurrency cap + Retry-After (ADMIT-P1).

One owner must not fill the shared sidecar pool and starve everyone else. The cap
keys on the NORMALIZED owner (survives token rotation, like the battle quota) and
is enforced in battle_begin BEFORE any sidecar work, returning 429 + Retry-After.

Tested by calling gateway.battle_begin directly (the cap check is pre-sidecar), so
these run without the node sidecar installed — unlike the full HTTP begin path.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from adx_showdown.sidecar import SidecarError
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, _normalize_owner
from agentdex_arena.gateway import ArenaGateway, BattleSession, BeginRequest, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

_OWNER = "eddie@oppie.xyz"


@pytest.fixture()
def gw(tmp_path: Path):
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    # create_app side-effects nothing we need, but mirrors the real wiring.
    create_app(gateway, sidecar_factory=lambda: None)
    return gateway


class _SentinelSidecar:
    """A sidecar whose start raises a NON-capacity error — proves battle_begin got
    PAST the per-owner cap (the cap would have 429'd before touching the sidecar)."""

    returncode = None

    async def request(self, op: str, **kwargs):
        raise SidecarError("sentinel: sidecar not really running")


def _token(gw: ArenaGateway, agent_key, *, owner: str = _OWNER, name: str = "PartnerBot") -> str:
    claims = ConsentClaims(
        token_id=uuid.uuid4().hex[:16],
        owner=owner,
        agent_name=name,
        agent_pubkey_hex=agent_key.public_key().public_bytes_raw().hex(),
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=gw.now(),
        expires_at=gw.now() + 7 * 86_400,
        confirmed_via="test",
    )
    return gw.authority.mint(claims)


def _begin_req(gw: ArenaGateway, token: str, agent_key) -> BeginRequest:
    start = gw.battle_start(token)
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    return BeginRequest(
        token=token, battle_nonce=start["battle_nonce"], pop_signature_hex=sig, lane="sandbox"
    )


def _dummy(owner: str, i: int) -> BattleSession:
    return BattleSession(
        battle_id=f"sandbox-dummy-{i}",
        claims_token_id="tok",
        visitor_name="PartnerBot",
        lane="sandbox",
        opponent="anchor-random",
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type]  — cap check only reads .owner
        opponent_policy=None,
        owner=owner,
    )


async def _call_begin(gw, req):
    return await gw.battle_begin(req, sidecar=_SentinelSidecar())


def test_per_owner_cap_429_with_retry_after(gw):
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    owner_norm = _normalize_owner(_OWNER)
    for i in range(3):  # default ARENA_MAX_BATTLES_PER_OWNER=3
        gw.sessions[f"sandbox-dummy-{i}"] = _dummy(owner_norm, i)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_call_begin(gw, req))
    assert ei.value.status_code == 429
    assert ei.value.headers["Retry-After"] == "5"


def test_ended_battles_do_not_count_toward_cap(gw):
    """Finished battles linger in self.sessions for the receipt — they must NOT
    count as live, else an owner who finished cap-many battles is 429'd forever
    until restart (PR #243 review)."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    owner_norm = _normalize_owner(_OWNER)
    for i in range(3):  # 3 FINISHED battles (default cap 3)
        s = _dummy(owner_norm, i)
        s.ended = {"winner": "x"}
        gw.sessions[f"done-{i}"] = s

    req = _begin_req(gw, token, agent_key)
    # No LIVE battles → must get PAST the cap (reaching the sentinel sidecar).
    with pytest.raises(SidecarError):
        asyncio.run(_call_begin(gw, req))


def test_429_leaves_nonce_usable_for_retry(gw):
    """A transient 429 must not consume the battle nonce, so a Retry-After replay
    of the same /battle/begin works instead of 403 unknown nonce (PR #243 review)."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    owner_norm = _normalize_owner(_OWNER)
    for i in range(3):
        gw.sessions[f"live-{i}"] = _dummy(owner_norm, i)

    req = _begin_req(gw, token, agent_key)
    nonce = req.battle_nonce
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_call_begin(gw, req))
    assert ei.value.status_code == 429
    # The nonce survived — a replay of the SAME POST is still admissible.
    assert gw.battle_nonces.get(nonce) is not None


class _BlockingSidecar:
    """A sidecar whose request() suspends until released — lets a begin hold its
    reservation while a second concurrent begin runs its synchronous cap check."""

    returncode = None

    def __init__(self) -> None:
        self.gate = asyncio.Event()

    async def request(self, op: str, **kwargs):
        await self.gate.wait()
        raise SidecarError("blocking sentinel released")


def test_concurrent_begins_cannot_burst_past_cap(gw):
    """Two simultaneous begins from one owner with 2 live battles (cap 3): the
    second must 429 because the first holds an in-flight RESERVATION (2 live + 1
    reserved = 3). Without the atomic reservation both would pass the count check
    before either published a session and burst past the cap (PR #243 review)."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    owner_norm = _normalize_owner(_OWNER)
    for i in range(2):  # 2 live, cap 3 → exactly one more slot
        gw.sessions[f"live-{i}"] = _dummy(owner_norm, i)

    sc = _BlockingSidecar()
    req1 = _begin_req(gw, token, agent_key)
    req2 = _begin_req(gw, token, agent_key)

    async def _run() -> None:
        t1 = asyncio.create_task(gw.battle_begin(req1, sidecar=sc))
        await asyncio.sleep(0.02)  # t1 reserves its slot then suspends in pack_team
        with pytest.raises(HTTPException) as ei:
            await gw.battle_begin(req2, sidecar=sc)  # 2 live + 1 reserved = 3 → 429
        assert ei.value.status_code == 429
        sc.gate.set()  # release t1 → it unwinds (SidecarError), freeing its slot
        with pytest.raises(SidecarError):
            await t1

    asyncio.run(_run())


def test_reclaimed_pending_begin_aborts_before_publish(gw):
    """If /healthz reclaims the sidecar route after start but before publication,
    battle_begin must return the interrupted signal and never publish a stale session."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    claims = gw.authority.verify(token, scope="battle")
    req = _begin_req(gw, token, agent_key)
    started_battle_ids: list[str] = []

    class _ReclaimedStartSidecar:
        returncode = None

        async def request(self, op: str, **kwargs):
            if op == "pack-team":
                return {"packed": "fakepacked"}
            if op == "start":
                battle_id = kwargs["battle"]
                started_battle_ids.append(battle_id)
                gw._mark_sidecar_evicted_battle(battle_id)
                return {"state": {}}
            raise AssertionError(f"unexpected sidecar op: {op}")

    with pytest.raises(HTTPException) as ei:
        asyncio.run(gw.battle_begin(req, sidecar=_ReclaimedStartSidecar()))

    assert ei.value.status_code == 409
    assert started_battle_ids
    battle_id = started_battle_ids[0]
    assert battle_id not in gw.sessions
    assert gw._interrupted.get(battle_id) == claims.token_id
    assert [event["type"] for event in gw.events.iter_events()] == []
    assert gw._owner_inflight == {}


def test_cap_keys_on_owner_not_token_id(gw):
    """5 live battles under a DIFFERENT owner do NOT count → this owner gets past
    the cap (and then hits the sentinel sidecar, proving it passed the check)."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    for i in range(5):
        gw.sessions[f"other-{i}"] = _dummy(_normalize_owner("someone-else@example.com"), i)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(SidecarError):  # got past the cap → reached the sentinel sidecar
        asyncio.run(_call_begin(gw, req))


def test_env_tightens_cap(gw, monkeypatch):
    monkeypatch.setenv("ARENA_MAX_BATTLES_PER_OWNER", "1")
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    gw.sessions["one"] = _dummy(_normalize_owner(_OWNER), 0)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_call_begin(gw, req))
    assert ei.value.status_code == 429


def _fork_src() -> dict:
    """Minimal replay record shape battle_fork reads (the cap reservation fires
    before any sidecar work, so this only needs to satisfy session construction)."""
    return {
        "opponent": "anchor-random",
        "tenant": "tok",
        "visitor": "PartnerBot",
        "seed": [1, 2, 3, 4],
        "teams": ("p1team", "p2team"),
        "explicit_opponent": False,
    }


def test_fork_obeys_owner_cap(gw):
    """Forking starts a NEW live sidecar battle, so it must hit the same per-owner
    cap — otherwise an owner forks finished battles into uncapped live sessions that
    are invisible to the cap (PR #243 review)."""
    owner_norm = _normalize_owner(_OWNER)
    for i in range(3):  # caller already at the default cap (3 live)
        gw.sessions[f"live-{i}"] = _dummy(owner_norm, i)

    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            gw.battle_fork(
                "sandbox-src", _fork_src(), turn=0, sidecar=_SentinelSidecar(), owner=_OWNER
            )
        )
    assert ei.value.status_code == 429


def test_fork_caps_on_forking_owner_not_source(gw):
    """The fork is capped against the FORKING caller's owner, so a caller under the
    cap gets PAST the reservation (then hits the sentinel sidecar)."""
    for i in range(3):  # 3 live under a DIFFERENT owner must not block this fork
        gw.sessions[f"other-{i}"] = _dummy(_normalize_owner("other@example.com"), i)

    with pytest.raises(SidecarError):  # past the cap → reached the sentinel sidecar
        asyncio.run(
            gw.battle_fork(
                "sandbox-src", _fork_src(), turn=0, sidecar=_SentinelSidecar(), owner=_OWNER
            )
        )


def test_failed_post_publish_fork_is_removed_from_cap(gw):
    """A failure AFTER the fork session is published (here _advance hits a protocol
    stall) must pop the session and release the reservation, so a dead battle never
    counts against the owner cap (PR #254 review)."""
    owner_norm = _normalize_owner(_OWNER)

    class _StallSidecar:
        returncode = None

        def __init__(self) -> None:
            self.ops: list[str] = []

        async def request(self, op: str, **kwargs):
            self.ops.append(op)
            return {"state": {}}  # empty → _advance stalls AFTER publish

    from fastapi import HTTPException as _HTTPException

    sc = _StallSidecar()
    with pytest.raises(_HTTPException):
        asyncio.run(gw.battle_fork("sandbox-src", _fork_src(), turn=0, sidecar=sc, owner=_OWNER))
    # Published-then-failed fork removed; reservation released → cap fully clean.
    assert gw._owner_inflight == {}
    assert not [bid for bid in gw.sessions if "fork" in bid]
    # The live sidecar battle was stopped before the handle was dropped (pool frees
    # capacity only on explicit stop) — PR #259 review.
    assert "stop" in sc.ops
    # And the owner can immediately admit a fresh battle (count is back to zero).
    gw._reserve_owner_slot(owner_norm)  # would raise 429 if the dead fork still counted
    gw._release_owner_slot(owner_norm)


def test_failed_session_dropped_even_when_stop_is_cancelled(gw):
    """If the post-publish stop() await is itself cancelled, the dead session must
    STILL be removed from the cap — the pop lives in a finally (PR #261 review)."""

    class _StopCancelsSidecar:
        returncode = None

        async def request(self, op: str, **kwargs):
            if op == "stop":
                raise asyncio.CancelledError()  # cleanup cancelled mid-teardown
            return {"state": {}}  # empty → _advance stalls AFTER publish

    raised: BaseException | None = None
    try:
        asyncio.run(
            gw.battle_fork(
                "sandbox-src", _fork_src(), turn=0, sidecar=_StopCancelsSidecar(), owner=_OWNER
            )
        )
    except BaseException as exc:  # noqa: BLE001 — capture whatever propagates
        raised = exc
    assert raised is not None
    # The finally popped the dead fork despite the cancelled stop.
    assert not [bid for bid in gw.sessions if "fork" in bid]
    assert gw._owner_inflight == {}


def test_post_publish_stop_reaches_sidecar_even_when_cleanup_cancelled(gw):
    """If the post-publish cleanup is cancelled mid-stop, the stop must still reach
    the (possibly pooled) sidecar — dispatched as a shielded task drained before the
    cancel propagates — so the slot's capacity is freed (PR #264 review)."""
    stop_done: list[int] = []
    stop_started = asyncio.Event()

    class _SlowStopSidecar:
        returncode = None

        async def request(self, op: str, **kwargs):
            if op == "stop":
                stop_started.set()
                await asyncio.sleep(0.02)  # routing the stop to the owning sidecar
                stop_done.append(1)
                return {"ok": True}
            return {"state": {}}  # empty → _advance stalls AFTER publish

    async def _run() -> None:
        sc = _SlowStopSidecar()
        t = asyncio.create_task(
            gw.battle_fork("sandbox-src", _fork_src(), turn=0, sidecar=sc, owner=_OWNER)
        )
        await stop_started.wait()  # we're now inside the post-publish stop
        t.cancel()
        with pytest.raises(BaseException):  # noqa: PT011,B017 — cancel propagates
            await t
        assert stop_done == [1]  # stop reached the sidecar despite the cancel
        assert not [bid for bid in gw.sessions if "fork" in bid]  # session dropped
        assert gw._owner_inflight == {}

    asyncio.run(_run())
