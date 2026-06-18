"""Class-A receipt atomicity — write-then-log fail-closed (ADX-P0-001).

A canonical EventLog append precedes every externally visible publish (session
registration, /replay record, returned receipt). When the append throws we FAIL
CLOSED: the live sidecar battle is stopped (no orphan unlogged battle), any live
session is marked ended-fatal so a retry sees the failure instead of a hang, and
the caller gets an opaque 500 instead of a receipt the log cannot back.

These tests pin the shared ``_append_or_fail_closed`` helper directly with a fake
sidecar, so they run WITHOUT the pokemon-showdown node sidecar — the lifecycle
integration coverage (begin / finish / fork end-to-end) lives in
test_visitor_surface.py behind the node gate.
"""

from __future__ import annotations

import asyncio
import time
import unittest.mock as mock
from pathlib import Path

import pytest
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import ArenaGateway, BattleSession, BeginRequest
from agentdex_engine.modules.arena import EventLog, RatingEvent, recompute_ladder
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException


def _gateway(tmp_path: Path) -> ArenaGateway:
    signing_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    return ArenaGateway(
        authority=ConsentAuthority(signing_key_hex=signing_key),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


class _StopRecordingSidecar:
    """Minimal async sidecar stub — records the (cmd, battle) of every request."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def request(self, cmd: str, **kwargs):
        self.calls.append((cmd, kwargs.get("battle")))
        return {}


def _session(sidecar: _StopRecordingSidecar) -> BattleSession:
    s = BattleSession(
        battle_id="sandbox-deadbeef",
        claims_token_id="tenant-1",
        visitor_name="Bot",
        lane="sandbox",
        opponent="brock",
        seed=[1, 7, 7, 7],
        sidecar=sidecar,  # type: ignore[arg-type]
        opponent_policy=None,
    )
    s.turns = 4
    return s


def test_append_failure_stops_sidecar_marks_fatal_and_500(tmp_path: Path) -> None:
    """Append throws -> live battle stopped, session ended-fatal, opaque 500."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)

    def boom(event_type, payload):
        raise OSError("mock disk full")

    gateway.events.append = boom  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            gateway._append_or_fail_closed(
                "battle_end",
                {"battle_id": session.battle_id},
                sidecar=sidecar,
                battle_id=session.battle_id,
                session=session,
            )
        )

    assert exc.value.status_code == 500
    # the live battle was torn down — no orphan live-but-unlogged battle
    assert ("stop", "sandbox-deadbeef") in sidecar.calls
    # a retry sees the failure, not a hang
    assert session.ended is not None
    assert "event log write failed" in session.ended.get("reason", "")
    assert session.ended.get("turns") == 4
    # nothing was committed to the durable log
    assert list(gateway.events.iter_events()) == []


def test_append_failure_without_session_still_stops_and_500(tmp_path: Path) -> None:
    """begin/fork call the helper before any session is published (session=None):
    the sidecar is still torn down and the caller still 500s."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()

    def boom(event_type, payload):
        raise OSError("mock disk full")

    gateway.events.append = boom  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            gateway._append_or_fail_closed(
                "battle_begin",
                {"battle_id": "sandbox-orphan"},
                sidecar=sidecar,
                battle_id="sandbox-orphan",
            )
        )
    assert exc.value.status_code == 500
    assert ("stop", "sandbox-orphan") in sidecar.calls


def test_append_success_returns_event_no_teardown(tmp_path: Path) -> None:
    """Happy path: the event is appended + returned; the sidecar is untouched."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()

    event = asyncio.run(
        gateway._append_or_fail_closed(
            "battle_begin",
            {"battle_id": "sandbox-1", "lane": "sandbox"},
            sidecar=sidecar,
            battle_id="sandbox-1",
        )
    )

    assert event["type"] == "battle_begin"
    assert sidecar.calls == []  # nothing stopped on the happy path
    assert [e["type"] for e in gateway.events.iter_events()] == ["battle_begin"]


def test_finish_group_append_failure_leaves_no_partial_receipt(tmp_path: Path) -> None:
    """Grouped finish append throws -> no replay, no artifact, no partial log."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)

    def boom(items):
        raise OSError("mock grouped write failure")

    gateway.events.append_many = boom  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            gateway._finish(
                session,
                {
                    "winner": "anchor-random",
                    "turns": 4,
                    "inputLog": ["line1", "line2"],
                    "keyLines": [],
                },
            )
        )

    assert exc.value.status_code == 500
    assert ("stop", "sandbox-deadbeef") in sidecar.calls
    assert session.battle_id not in gateway.replays
    assert not (gateway.artifacts_dir / f"{session.battle_id}.inputlog.json").exists()
    assert list(gateway.events.iter_events()) == []
    assert session.ended is not None
    assert "event log write failed" in session.ended.get("reason", "")


def test_finish_artifact_write_failure_keeps_public_receipt_shape(tmp_path: Path) -> None:
    """After the durable group commits, artifact I/O must not leave a skeletal
    internal ended marker that turns retry responses into malformed receipts."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)
    gateway.artifacts_dir = tmp_path / "not-a-dir"
    gateway.artifacts_dir.write_text("blocks mkdir")

    receipt = asyncio.run(
        gateway._finish(
            session,
            {
                "winner": "anchor-random",
                "turns": 4,
                "inputLog": ["line1", "line2"],
                "keyLines": [],
            },
        )
    )

    assert receipt["status"] == "ended"
    assert session.ended == receipt
    assert session.battle_id in gateway.replays
    assert [event["type"] for event in gateway.events.iter_events()] == ["battle_end"]


def test_exhausted_rated_quota_rejected_before_orphan_append(tmp_path: Path) -> None:
    """Rated quota PREFLIGHT (PR #181): an ALREADY-exhausted caller is rejected by
    the read-only check_quota guard BEFORE sidecar.start + the durable battle_begin
    append, so a flood of fresh-nonce retries cannot fill the EventLog with orphan
    rated begins. (The authoritative spend_quota debit still follows AFTER a
    successful append — Class A append-before-publish + Class B spend-after-success
    are preserved for battles that actually run; see test_quota_spend_after_success.)

    With quota already exhausted at preflight:
    - NO battle_begin row in the durable log (append never reached)
    - sidecar was NOT touched (no start, hence no stop / orphan live battle)
    - 403 raised (not 500)
    - battle_id NOT in gateway.sessions (session never published)
    """
    agent_key = Ed25519PrivateKey.generate()
    agent_pubkey_hex = agent_key.public_key().public_bytes_raw().hex()
    signing_key_hex = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing_key_hex)

    claims = ConsentClaims(
        token_id="test-tok-rated-p2a",
        owner="tester@example.com",
        agent_name="TestBotP2A",
        agent_pubkey_hex=agent_pubkey_hex,
        scopes=["battle"],
        quotas={"battle": 1},
        issued_at=time.time(),
        expires_at=time.time() + 3600,
        confirmed_via="test",
    )
    token = authority.mint(claims)

    # Pre-exhaust: 1/1 battle slots used today.
    day = time.strftime("%Y%m%d", time.gmtime())
    authority.quota_used[f"tester@example.com:battle:{day}"] = 1

    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )

    nonce = "rated-nonce-p2a-test"
    gateway.battle_nonces[nonce] = claims.token_id
    pop_challenge = f"arena-pop:{claims.token_id}:{nonce}".encode()
    sig_hex = agent_key.sign(pop_challenge).hex()

    req = BeginRequest(
        token=token,
        battle_nonce=nonce,
        pop_signature_hex=sig_hex,
        lane="rated",
    )

    sidecar_calls: list[str] = []
    pack_team_calls: list = []

    class _FakeSidecar:
        async def request(self, cmd: str, **kwargs):
            sidecar_calls.append(cmd)
            return {"state": {}}

    async def _fake_pack_team(sidecar, team_spec):
        pack_team_calls.append(team_spec)
        return "fakepacked"

    with mock.patch("agentdex_arena.gateway.pack_team", _fake_pack_team):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(gateway.battle_begin(req, sidecar=_FakeSidecar()))

    assert exc.value.status_code == 403
    # preflight fired at the TOP — before any team/sidecar work AND before the append
    assert pack_team_calls == []  # no team resolution work burned (PR #230 review)
    assert sidecar_calls == []  # the sidecar was never touched
    assert [e["type"] for e in gateway.events.iter_events()] == []  # NO orphan begin row
    # session was never published
    assert all("rated" not in bid for bid in gateway.sessions)


def test_rated_finish_delta_brackets_only_its_own_append(tmp_path: Path, monkeypatch) -> None:
    """ADX-P1-007: concurrent same-visitor rated finishes must not let one receipt's
    published_delta absorb the other battle's rating movement.

    The bug: _finish reads `before = recompute_ladder()`, awaits the durable append,
    then reads `after`. Without serialization, a second same-visitor finish can commit
    its rating period BETWEEN this finish's before/after snapshots, so the first
    receipt reports BOTH battles' movement (r2-r0) instead of only its own (r1-r0).
    The per-visitor lock (gateway._finish_locks) brackets the whole window.

    This test forces the interleave by gating the first finish's append until the
    second finish has been launched. The assertion is implementation-independent:
    the first receipt's delta must equal the standalone single-battle movement, and
    the two receipts' deltas must TELESCOPE to the total two-battle movement (each
    battle counted exactly once, no double-count).
    """
    gateway = _gateway(tmp_path)
    visitor = "RaceBot"
    opponent = "anchor-max_damage"
    register_items = [
        ("register", {"name": visitor, "frozen": False}),
        ("register", {"name": opponent, "frozen": True}),
    ]
    gateway.events.append_many(register_items)
    gateway._registered.update({visitor, opponent})

    # Expose raw rating movement so the bracket is verified directly, independent of
    # the public 2*RD inconclusive rail.
    monkeypatch.setattr(
        "agentdex_arena.gateway.Ladder.published_delta",
        staticmethod(lambda before, after: after.rating - before.rating),
    )

    def end_payload(label: str) -> dict[str, object]:
        return {"winner": visitor, "turns": 12, "inputLog": [f"{label}-1", f"{label}-2"]}

    def session(label: str) -> BattleSession:
        return BattleSession(
            battle_id=f"rated-{label}",
            claims_token_id="tenant-race",
            visitor_name=visitor,
            lane="rated",
            opponent=opponent,
            seed=[1, 2, 3, 4],
            sidecar=None,  # type: ignore[arg-type]
            opponent_policy=None,
            p1_team="visitor-team",
            p2_team="opponent-team",
            visitor_choices=["move 1", "move 2", "move 3", "move 4"],
        )

    # Independently compute the standalone first-battle movement (r1-r0) and the
    # cumulative two-battle movement (r2-r0) on a parallel ladder. Glicko depends
    # only on win/loss + opponent, not the input_log digest, so fixed digests are fine.
    def _period(bid: str) -> tuple[str, dict]:
        return (
            "period",
            {
                "events": [
                    RatingEvent(
                        battle_id=bid,
                        p1=visitor,
                        p2=opponent,
                        winner=visitor,
                        input_log_blake2b16="a" * 32,
                    ).model_dump()
                ]
            },
        )

    expected_log = EventLog(tmp_path / "expected.jsonl")
    expected_log.append_many(register_items)
    r0 = recompute_ladder(expected_log.path).rating(visitor)
    expected_log.append_many([_period("exp-1")])
    r1 = recompute_ladder(expected_log.path).rating(visitor)
    expected_log.append_many([_period("exp-2")])
    r2 = recompute_ladder(expected_log.path).rating(visitor)
    expected_first_delta = round(r1.rating - r0.rating, 1)
    expected_total_delta = round(r2.rating - r0.rating, 1)

    # Gate the first finish's durable append open until the second finish is launched,
    # so without the lock the second would commit inside the first's before/after window.
    original_helper = gateway._append_many_or_fail_closed
    first_reached_append = asyncio.Event()
    allow_first_append = asyncio.Event()

    async def gated_append_many(items, *, sidecar=None, battle_id=None, session=None):
        if battle_id == "rated-original":
            first_reached_append.set()
            await allow_first_append.wait()
        return await original_helper(items, sidecar=sidecar, battle_id=battle_id, session=session)

    gateway._append_many_or_fail_closed = gated_append_many  # type: ignore[method-assign]

    async def run_race():
        first_task = asyncio.create_task(gateway._finish(session("original"), end_payload("a")))
        # With the lock, the second finish blocks on the per-visitor lock the first
        # holds; without it, the second would race straight into its own recompute.
        await first_reached_append.wait()
        second_task = asyncio.create_task(gateway._finish(session("concurrent"), end_payload("b")))
        await asyncio.sleep(0)
        allow_first_append.set()
        return await first_task, await second_task

    first_receipt, second_receipt = asyncio.run(run_race())

    first_delta = first_receipt["rating"]["published_delta"]
    second_delta = second_receipt["rating"]["published_delta"]
    # First receipt reflects ONLY its own battle (the bug would make it == total).
    assert first_delta == expected_first_delta
    # The two deltas telescope to the total movement — neither double-counts.
    assert round(first_delta + second_delta, 1) == expected_total_delta


def test_finish_cancelled_while_waiting_lock_leaves_no_partial_receipt(tmp_path: Path) -> None:
    """ADX-P1-007 follow-up (PR #269 review 3433532481): a second same-visitor rated
    finish that is CANCELLED while suspended on the per-visitor lock must leave
    session.ended is None — no unbacked partial receipt that /state /choose would
    surface. Guards the append-before-publish invariant against the lock wait the
    rating-serialization added (session.ended is now set only at the publish phase,
    after the durable append, never as an early marker)."""
    gateway = _gateway(tmp_path)
    visitor = "WaitBot"
    opponent = "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})

    def _session(label: str) -> BattleSession:
        return BattleSession(
            battle_id=f"rated-{label}",
            claims_token_id="tenant-wait",
            visitor_name=visitor,
            lane="rated",
            opponent=opponent,
            seed=[1, 2, 3, 4],
            sidecar=None,  # type: ignore[arg-type]
            opponent_policy=None,
            p1_team="vt",
            p2_team="ot",
            visitor_choices=["move 1", "move 2", "move 3", "move 4"],
        )

    end = {"winner": visitor, "turns": 12, "inputLog": ["a", "b"]}

    # Gate the FIRST finish open inside its critical section so it holds the lock
    # while the second contends.
    original = gateway._append_many_or_fail_closed
    first_in_section = asyncio.Event()
    release_first = asyncio.Event()

    async def gated(items, *, sidecar=None, battle_id=None, session=None):
        if battle_id == "rated-first":
            first_in_section.set()
            await release_first.wait()
        return await original(items, sidecar=sidecar, battle_id=battle_id, session=session)

    gateway._append_many_or_fail_closed = gated  # type: ignore[method-assign]

    async def run() -> BattleSession:
        first = asyncio.create_task(gateway._finish(_session("first"), dict(end)))
        await first_in_section.wait()  # first holds the lock
        second_session = _session("second")
        second = asyncio.create_task(gateway._finish(second_session, dict(end)))
        await asyncio.sleep(0.05)  # let second reach `await rating_lock.acquire()` and block
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        # the cancelled-mid-wait finish published NOTHING
        assert second_session.ended is None
        assert "rated-second" not in gateway.replays
        release_first.set()
        await first
        return second_session

    asyncio.run(run())
