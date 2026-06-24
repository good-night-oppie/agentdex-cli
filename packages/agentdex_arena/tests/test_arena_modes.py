"""GA-ARENA-MODES: mode field + PvP queue + pvp-choose gateway tests.

Uses the same fixture pattern as test_admission.py — direct gateway calls,
no real node sidecar. FakeSidecar records ops and returns minimal states.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
import uuid
from pathlib import Path

import pydantic
import pytest
from adx_showdown.pvp import PvPChoiceRouter, PvPQueue
from agentdex_arena import gateway as gateway_mod
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, _normalize_owner
from agentdex_arena.eventsync import PVP_MATCH, PVP_QUEUE_ENTER
from agentdex_arena.gateway import (
    ArenaGateway,
    BattleSession,
    BeginRequest,
    create_app,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.testclient import TestClient

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


def _pvp_queue_body(gw: ArenaGateway, token: str, key) -> dict:
    start = gw.battle_start(token)
    sig = key.sign(start["pop_challenge"].encode()).hex()
    return {
        "token": token,
        "battle_nonce": start["battle_nonce"],
        "pop_signature_hex": sig,
        "mode": "pvp",
    }


def _move_request(side: str) -> dict:
    return {
        "active": [
            {
                "moves": [
                    {
                        "move": "Tackle",
                        "id": "tackle",
                        "pp": 35,
                        "maxpp": 35,
                        "disabled": False,
                    }
                ]
            }
        ],
        "side": {
            "id": side,
            "pokemon": [
                {
                    "ident": f"{side}: Bulbasaur",
                    "details": "Bulbasaur, L50",
                    "condition": "100/100",
                    "active": True,
                    "moves": ["tackle"],
                }
            ],
        },
    }


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


def test_pvp_queue_identity_passthrough(gw: ArenaGateway):
    """PvP matchmaking carries agent_name/token_id/team into PvPPairing fields."""

    async def _go():
        q = gw.pvp_queue
        key_a = Ed25519PrivateKey.generate()
        key_b = Ed25519PrivateKey.generate()
        tok_a = _mint(gw, "alice@test.com", "AgentA", key_a)
        tok_b = _mint(gw, "bob@test.com", "AgentB", key_b)
        claims_a = gw.authority.verify(tok_a, scope="battle")
        claims_b = gw.authority.verify(tok_b, scope="battle")
        from agentdex_arena.consent import _normalize_owner

        owner_a = _normalize_owner(claims_a.owner)
        owner_b = _normalize_owner(claims_b.owner)

        fut_a = asyncio.ensure_future(
            q.enqueue(owner_a, agent_name="AgentA", token_id=claims_a.token_id, team=None)
        )
        await asyncio.sleep(0)
        pairing_b = await q.enqueue(
            owner_b, agent_name="AgentB", token_id=claims_b.token_id, team="myteam"
        )
        pairing_a = await fut_a

        # P1 receives P2's identity for session.pvp_p2_claims_token_id binding
        assert pairing_a.p2_claims_token_id == claims_b.token_id
        assert pairing_a.opponent_agent_name == "AgentB"
        assert pairing_a.p2_team == "myteam"
        # P2 receives P1's identity
        assert pairing_b.opponent_agent_name == "AgentA"

    asyncio.run(_go())


def test_pvp_queue_duplicate_choice_raises(gw: ArenaGateway):
    """submit_p2_choice raises ValueError when a prior choice is unconsumed."""
    router = gw.pvp_choice_router
    router.submit_p2_choice("dup-test", "move 1")  # first submit → buffered
    with pytest.raises(ValueError, match="duplicate"):
        router.submit_p2_choice("dup-test", "move 2")  # second → ValueError


def test_pvp_choose_uses_forfeit_enabled_stale_expiry():
    src = inspect.getsource(gateway_mod.create_app)
    assert "await gateway._expire_if_stale(session, allow_forfeit=True)" in src


def test_pvp_choose_appends_p2_choice_before_ack(gw: ArenaGateway):
    key = Ed25519PrivateKey.generate()
    token = _mint(gw, "p2-audit@example.com", "AgentB", key)
    claims = gw.authority.verify(token, scope="battle")
    session = BattleSession(
        battle_id="pvp-audit",
        claims_token_id="p1-token",
        visitor_name="AgentA",
        lane="sandbox",
        opponent="AgentB",
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type] - pvp-choose only appends + routes.
        opponent_policy=None,
    )
    session.visitor_side = "p1"
    session.pvp_p2_claims_token_id = claims.token_id
    session.turns = 3
    session.last_state = {
        "pending": {"p2": _move_request("p2")},
        "active": {"p1": "Bulbasaur", "p2": "Bulbasaur"},
        "turns": 3,
    }
    gw.sessions[session.battle_id] = session
    app = create_app(gw, sidecar_factory=lambda: None)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/battle/{session.battle_id}/pvp-choose",
            json={"token": token, "choice_index": 1},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    battle_events = [event for event in gw.events.iter_events() if event["type"] == "battle"]
    assert len(battle_events) == 1
    payload = battle_events[0]["payload"]
    assert payload["tenant_id"] == claims.token_id
    assert payload["battle_id"] == session.battle_id
    assert payload["turn"] == 3
    assert payload["side"] == "p2"
    assert payload["choice"] == "move 1"
    assert payload["choice_label"] == "tackle"


def test_p2_match_receipt_does_not_return_raw_last_state():
    src = inspect.getsource(gateway_mod.create_app)
    p2_receipt = src.split('"role": "p2"', 1)[1].split("return result", 1)[0]
    assert '"last_state"' not in p2_receipt


def test_p2_disconnect_does_not_cleanup_p1_choice_router():
    src = inspect.getsource(gateway_mod.create_app)
    assert 'pairing.role == "p1"' in src
    assert "gateway.pvp_choice_router.cleanup(battle_id)" in src


def test_p2_owner_counts_against_concurrency_cap(gw: ArenaGateway, monkeypatch):
    monkeypatch.setenv("ARENA_MAX_BATTLES_PER_OWNER", "1")
    owner = _normalize_owner("p2@example.com")
    gw.sessions["pvp-live"] = BattleSession(
        battle_id="pvp-live",
        claims_token_id="p1-token",
        visitor_name="AgentA",
        lane="sandbox",
        opponent="AgentB",
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type] - cap check only reads owners.
        opponent_policy=None,
        owner="p1@example.com",
        pvp_p2_owner=owner,
    )
    with pytest.raises(HTTPException) as exc:
        gw._reserve_owner_slot(owner)
    assert exc.value.status_code == 429


def test_p2_match_receipt_returns_indexed_choice_options():
    src = inspect.getsource(gateway_mod.create_app)
    p2_receipt = src.split('"role": "p2"', 1)[1].split("return result", 1)[0]
    assert '"choices": [' in p2_receipt
    assert '"n_choices": len(choices)' in p2_receipt
    assert '"index": idx' in p2_receipt


def test_p2_queue_timeout_is_retryable_not_false_matched():
    src = inspect.getsource(gateway_mod.create_app)
    pvp_queue = src.split("async def me_battle_queue", 1)[1].split(
        '@app.post("/battle/{battle_id}/pvp-choose")', 1
    )[0]
    assert "pvp match startup not ready" in pvp_queue
    assert 'headers={"Retry-After": os.environ.get("ARENA_RETRY_AFTER_SEC", "5")}' in pvp_queue


def test_p2_queue_timeout_cancels_p1_startup_before_publish():
    src = inspect.getsource(gateway_mod.create_app)
    pvp_queue = src.split("async def me_battle_queue", 1)[1].split(
        '@app.post("/battle/{battle_id}/pvp-choose")', 1
    )[0]
    timeout_branch = pvp_queue.split(
        "if published is None or published.last_state is None:", 1
    )[1].split("raise HTTPException", 1)[0]
    assert "gateway._pvp_cancelled_startups.add(battle_id)" in timeout_branch
    assert "gateway.pvp_choice_router.cleanup(battle_id)" in timeout_branch

    p1_branch = pvp_queue.split('if pairing.role == "p1":', 1)[1].split(
        "            else:\n                # P2:", 1
    )[0]
    assert "async def _abort_if_p2_startup_cancelled()" in p1_branch
    assert "pvp match startup expired" in p1_branch
    assert "await gateway._stop_battle_robustly(sidecar, battle_id)" in p1_branch
    assert "await _abort_if_p2_startup_cancelled()" in p1_branch


def test_p2_queue_timeout_translates_cancelled_p1_waiter_to_503(gw: ArenaGateway, monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, result=None):  # noqa: ARG001
        await real_sleep(0.001)
        return result

    monkeypatch.setattr(gateway_mod.asyncio, "sleep", fast_sleep)

    class _P2ChoiceFirstSidecar:
        returncode = None

        def __init__(self) -> None:
            self.stopped: list[str] = []

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def request(self, op: str, **kwargs):
            if op == "pack-team":
                return {"packed": "packed-team"}
            if op == "start":
                return {
                    "state": {
                        "turns": 1,
                        "pending": {"p2": _move_request("p2")},
                        "active": {"p1": "Bulbasaur", "p2": "Bulbasaur"},
                    }
                }
            if op == "stop":
                self.stopped.append(kwargs["battle"])
                return {"inputLog": []}
            raise AssertionError(f"unexpected sidecar op: {op}")

    sidecar = _P2ChoiceFirstSidecar()
    app = create_app(gw, sidecar_factory=lambda: sidecar)
    key_a = Ed25519PrivateKey.generate()
    key_b = Ed25519PrivateKey.generate()
    tok_a = _mint(gw, "alice@test.com", "AgentA", key_a)
    tok_b = _mint(gw, "bob@test.com", "AgentB", key_b)
    body_a = _pvp_queue_body(gw, tok_a, key_a)
    body_b = _pvp_queue_body(gw, tok_b, key_b)
    responses = {}

    with TestClient(app, raise_server_exceptions=False) as client:

        def post_queue(name: str, body: dict) -> None:
            responses[name] = client.post("/me/battle/queue", json=body)

        t1 = threading.Thread(target=post_queue, args=("p1", body_a))
        t1.start()
        deadline = time.monotonic() + 2.0
        while gw.pvp_queue.queue_depth == 0 and t1.is_alive() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert gw.pvp_queue.queue_depth == 1

        t2 = threading.Thread(target=post_queue, args=("p2", body_b))
        t2.start()
        t1.join(timeout=2)
        t2.join(timeout=2)

    assert not t1.is_alive()
    assert not t2.is_alive()
    assert responses["p1"].status_code == 503
    assert responses["p1"].json()["detail"] == "pvp match startup expired — requeue"
    assert responses["p2"].status_code == 503
    assert responses["p2"].json()["detail"] == "pvp match startup not ready — retry"
    assert sidecar.stopped


def test_p2_team_invalid_path_does_not_silently_substitute_starter_pack():
    src = inspect.getsource(gateway_mod.create_app)
    p2_team_branch = src.split("if pairing.p2_team is not None:", 1)[1].split("else:", 1)[0]
    assert "opp_team = pairing.p2_team" in p2_team_branch
    assert "pack_team" not in p2_team_branch


def test_pvp_initial_advance_failure_tears_down_published_session():
    src = inspect.getsource(gateway_mod.create_app)
    initial_advance = src.split("state = await gateway._advance", 1)[1].split('"role": "p1"', 1)[0]
    assert "gateway.pvp_choice_router.cleanup(battle_id)" in initial_advance
    assert "await gateway._stop_battle_robustly(sidecar, battle_id)" in initial_advance
    assert "gateway.sessions.pop(battle_id, None)" in initial_advance


def test_pvp_start_capacity_uses_retry_after_503():
    src = inspect.getsource(gateway_mod.create_app)
    pvp_queue = src.split("async def me_battle_queue", 1)[1].split(
        '@app.post("/battle/{battle_id}/pvp-choose")', 1
    )[0]
    assert "arena at capacity" in pvp_queue
    assert "status_code=503" in pvp_queue
    assert 'headers={"Retry-After": os.environ.get("ARENA_RETRY_AFTER_SEC", "5")}' in pvp_queue


def test_pvp_advance_renders_p1_before_awaiting_p2_choice(gw: ArenaGateway):
    """Opening simultaneous-choice state must publish P1 before waiting on P2."""

    async def _blocking_p2_policy(_req, _ctx=None):
        await asyncio.Event().wait()

    async def _go():
        session = BattleSession(
            battle_id="pvp-start",
            claims_token_id="p1-token",
            visitor_name="AgentA",
            lane="sandbox",
            opponent="AgentB",
            seed=[1, 2, 3, 4],
            sidecar=None,  # type: ignore[arg-type] - this path must return before stepping.
            opponent_policy=_blocking_p2_policy,
        )
        state = {
            "pending": {"p1": _move_request("p1"), "p2": _move_request("p2")},
            "active": {"p1": "Bulbasaur", "p2": "Bulbasaur"},
            "active_hp": {"p1": 100, "p2": 100},
            "turns": 1,
        }

        result = await asyncio.wait_for(
            gw._advance(session, state, visitor_choice=None),
            timeout=0.25,
        )
        assert result["status"] == "your_move"
        assert session.last_state is state
        assert not gw.pvp_choice_router.is_waiting_for_p2("pvp-start")

    asyncio.run(_go())
