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
import contextlib
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


def test_advance_shields_finish_so_a_cancelled_choose_still_publishes(tmp_path: Path) -> None:
    """PR #276 review 3434024561: a finish reached via _advance (the /choose path)
    must run to completion even if the request is CANCELLED while suspended on the
    per-visitor rating lock. Otherwise a battle that already ended is stranded as
    pending=None + ended=None and /state 409s until stale-expiry forfeits it,
    losing the real result. _advance shields _finish, so the cancel propagates to
    the caller while the durable receipt + session.ended still land."""
    gateway = _gateway(tmp_path)
    visitor = "ShieldBot"
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
            claims_token_id="tenant-shield",
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

    # Hold the first finish inside its critical section so it owns the lock while
    # the second (driven through _advance) contends and is then cancelled.
    original = gateway._append_many_or_fail_closed
    first_in_section = asyncio.Event()
    release_first = asyncio.Event()

    async def gated(items, *, sidecar=None, battle_id=None, session=None):
        if battle_id == "rated-first":
            first_in_section.set()
            await release_first.wait()
        return await original(items, sidecar=sidecar, battle_id=battle_id, session=session)

    gateway._append_many_or_fail_closed = gated  # type: ignore[method-assign]

    async def run() -> None:
        first = asyncio.create_task(gateway._finish(_session("first"), dict(end)))
        await first_in_section.wait()  # first holds the per-visitor lock
        second_session = _session("second")
        # Drive via _advance with an already-terminal state so the shield applies.
        second = asyncio.create_task(
            gateway._advance(second_session, {"end": dict(end)}, visitor_choice=None)
        )
        await asyncio.sleep(0.05)  # second reaches the shielded finish's lock wait
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second  # the request is cancelled...
        assert second_session.ended is None  # ...and hasn't published yet (still blocked)
        # A STRONG reference to the backgrounded finish survives the cancel, so
        # the loop's weak task ref can't GC it mid-wait (PR #289 review 3435535482).
        assert second_session.finish_task is not None
        assert not second_session.finish_task.done()

        release_first.set()
        await first
        # ...but the shielded finish keeps going and lands the real receipt. Poll
        # for BOTH the receipt AND the cleared ref — the done-callback that nulls
        # finish_task runs a tick AFTER _finish sets session.ended (call_soon).
        for _ in range(200):
            if second_session.ended is not None and second_session.finish_task is None:
                break
            await asyncio.sleep(0.01)
        assert second_session.ended is not None, "shielded finish must complete despite the cancel"
        assert second_session.ended["winner"] == visitor
        assert "rated-second" in gateway.replays
        # The done-callback released the strong ref once the finish completed.
        assert second_session.finish_task is None

    asyncio.run(run())


def test_expire_if_stale_skips_while_finish_outstanding(tmp_path: Path) -> None:
    """PR #289 review 3435535478: while a shielded finish is in-flight
    (session.finish_task set, session.ended still None), _expire_if_stale must NOT
    forfeit — otherwise it queues a second _finish that double-appends battle_end
    and overwrites the real result with a bogus timeout forfeit."""
    gateway = _gateway(tmp_path)
    session = BattleSession(
        battle_id="rated-inflight",
        claims_token_id="tenant-x",
        visitor_name="InFlightBot",
        lane="rated",
        opponent="anchor-max_damage",
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type]
        opponent_policy=None,
    )
    session.last_touch = 0.0  # ancient — would normally trip the turn-budget forfeit

    async def run() -> None:
        # An outstanding shielded finish, modelled by a pending task.
        dummy = asyncio.ensure_future(asyncio.sleep(60))
        session.finish_task = dummy
        try:
            await gateway._expire_if_stale(session)
            assert session.ended is None, "must not forfeit while a finish is outstanding"
            assert not any(e["type"] == "battle_end" for e in gateway.events.iter_events()), (
                "no second battle_end may be appended"
            )
        finally:
            dummy.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dummy
            session.finish_task = None

    asyncio.run(run())


def test_replay_rehydrates_from_artifact_after_restart(tmp_path: Path) -> None:
    """ADX-P0-001 residual: self.replays is in-memory only (reset on boot), so a
    restart would 404 /replay for every prior-process battle despite its receipt
    promising one. _finish persists a durable <id>.replay.json; load_replay
    rehydrates from it when the in-memory map misses (post-restart)."""
    g1 = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)
    asyncio.run(
        g1._finish(
            session,
            {"winner": "anchor-random", "turns": 4, "inputLog": ["l1", "l2"], "keyLines": []},
        )
    )
    bid = session.battle_id
    assert bid in g1.replays
    assert (g1.artifacts_dir / f"{bid}.replay.json").exists()

    # Simulate a restart: a fresh gateway over the SAME events_path + artifacts_dir.
    g2 = _gateway(tmp_path)
    assert bid not in g2.replays  # the in-memory replay map starts empty on boot
    rec = g2.load_replay(bid)
    assert rec is not None
    assert rec["input_log"] == ["l1", "l2"]
    assert rec["winner"] == "anchor-random"
    assert g2.replays[bid] is rec  # cached for subsequent hits

    # Misses + path-traversal safety return None, never raise / read outside the dir.
    assert g2.load_replay("no-such-battle") is None
    assert g2.load_replay("../../etc/passwd") is None
