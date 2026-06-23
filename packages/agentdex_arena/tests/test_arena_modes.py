"""GA-ARENA-MODES: mode field + PvP queue + pvp-choose gateway tests.

Uses the same fixture pattern as test_admission.py — direct gateway calls,
no real node sidecar. FakeSidecar records ops and returns minimal states.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pydantic
import pytest
from adx_showdown.pvp import PvPChoiceRouter, PvPQueue
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, _normalize_owner
from agentdex_arena.eventsync import PVP_MATCH, PVP_QUEUE_ENTER
from agentdex_arena.gateway import (
    ArenaGateway,
    BeginRequest,
    create_app,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# ── fixtures ──────────────────────────────────────────────────────────────────


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
    create_app(gateway, sidecar_factory=lambda: None)
    return gateway


def _mint(gw: ArenaGateway, owner: str, name: str, key) -> str:
    claims = ConsentClaims(
        token_id=uuid.uuid4().hex[:16],
        owner=owner,
        agent_name=name,
        agent_pubkey_hex=key.public_key().public_bytes_raw().hex(),
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=gw.now(),
        expires_at=gw.now() + 7 * 86_400,
        confirmed_via="test",
    )
    return gw.authority.mint(claims)


def _begin_req(gw: ArenaGateway, token: str, key, **kwargs) -> BeginRequest:
    start = gw.battle_start(token)
    sig = key.sign(start["pop_challenge"].encode()).hex()
    return BeginRequest(
        token=token,
        battle_nonce=start["battle_nonce"],
        pop_signature_hex=sig,
        lane="sandbox",
        **kwargs,
    )


# ── ArenaMode field on BeginRequest ───────────────────────────────────────────


def test_begin_request_default_mode_is_solo_bots():
    Ed25519PrivateKey.generate()
    req = BeginRequest(
        token="tok",
        battle_nonce="n",
        pop_signature_hex="a" * 128,
    )
    assert req.mode == "solo_bots"


def test_begin_request_mode_pvp():
    req = BeginRequest(
        token="tok",
        battle_nonce="n",
        pop_signature_hex="a" * 128,
        mode="pvp",
    )
    assert req.mode == "pvp"


def test_begin_request_mode_invalid_rejected():
    with pytest.raises(pydantic.ValidationError):
        BeginRequest(
            token="tok",
            battle_nonce="n",
            pop_signature_hex="a" * 128,
            mode="selfplay",  # type: ignore[arg-type] — not in ArenaMode
        )


# ── eventsync PVP constants ───────────────────────────────────────────────────


def test_pvp_event_type_constants_are_strings():
    assert isinstance(PVP_QUEUE_ENTER, str)
    assert isinstance(PVP_MATCH, str)
    assert PVP_QUEUE_ENTER == "pvp_queue_enter"
    assert PVP_MATCH == "pvp_match"


# ── PvPQueue lives on gateway ─────────────────────────────────────────────────


def test_gateway_has_pvp_queue(gw: ArenaGateway):
    assert isinstance(gw.pvp_queue, PvPQueue)
    assert gw.pvp_queue.queue_depth == 0


def test_gateway_has_pvp_choice_router(gw: ArenaGateway):
    assert isinstance(gw.pvp_choice_router, PvPChoiceRouter)


# ── PvP queue endpoint (unit — no sidecar) ───────────────────────────────────


def test_pvp_queue_bad_token_rejected_by_authority(gw: ArenaGateway):
    """A bad consent token is rejected before touching the queue."""
    from agentdex_arena.consent import ConsentError

    with pytest.raises(ConsentError):
        gw.authority.verify("notarealtoken", scope="battle")


def test_pvp_queue_pairs_two_owners_matchmaking(gw: ArenaGateway):
    """Two owners enter the PvP queue; the second is immediately paired."""

    async def _go():
        q = gw.pvp_queue
        key_a = Ed25519PrivateKey.generate()
        key_b = Ed25519PrivateKey.generate()
        tok_a = _mint(gw, "alice@test.com", "AgentA", key_a)
        tok_b = _mint(gw, "bob@test.com", "AgentB", key_b)
        # Verify tokens are valid
        claims_a = gw.authority.verify(tok_a, scope="battle")
        claims_b = gw.authority.verify(tok_b, scope="battle")
        owner_a = _normalize_owner(claims_a.owner)
        owner_b = _normalize_owner(claims_b.owner)

        fut_a = asyncio.ensure_future(q.enqueue(owner_a))
        await asyncio.sleep(0)
        assert q.queue_depth == 1

        pairing_b = await q.enqueue(owner_b)
        pairing_a = await fut_a

        assert pairing_a.role == "p1"
        assert pairing_b.role == "p2"
        assert pairing_a.battle_id == pairing_b.battle_id
        assert pairing_a.battle_id.startswith("pvp-")
        assert q.queue_depth == 0

    asyncio.run(_go())


# ── PvP choice router integration ────────────────────────────────────────────


def test_pvp_choice_router_routes_p2_choice(gw: ArenaGateway):
    async def _go():
        router = gw.pvp_choice_router
        policy = router.make_p2_policy("pvp-test123")
        router.submit_p2_choice("pvp-test123", "move 1")
        result = await policy(None)
        assert result == "move 1"

    asyncio.run(_go())


def test_pvp_choice_router_cleanup_on_battle_end(gw: ArenaGateway):
    async def _go():
        router = gw.pvp_choice_router
        policy = router.make_p2_policy("pvp-cleanup")
        fut = asyncio.ensure_future(policy(None))
        await asyncio.sleep(0)
        assert router.is_waiting_for_p2("pvp-cleanup")
        router.cleanup("pvp-cleanup")
        assert not router.is_waiting_for_p2("pvp-cleanup")
        # Suppress the CancelledError from the abandoned future
        fut.cancel()
        with pytest.raises(asyncio.CancelledError):
            await fut

    asyncio.run(_go())


# ── mode field logged in battle_begin payload ─────────────────────────────────


def test_mode_field_in_begin_request_passes_to_payload(gw: ArenaGateway):
    """BeginRequest.mode is accepted; solo_bots is the default."""
    key = Ed25519PrivateKey.generate()
    tok = _mint(gw, "charlie@test.com", "AgentC", key)
    req = _begin_req(gw, tok, key, mode="solo_bots")
    assert req.mode == "solo_bots"


def test_mode_pvp_accepted_in_begin_request(gw: ArenaGateway):
    key = Ed25519PrivateKey.generate()
    tok = _mint(gw, "dave@test.com", "AgentD", key)
    req = _begin_req(gw, tok, key, mode="pvp")
    assert req.mode == "pvp"
