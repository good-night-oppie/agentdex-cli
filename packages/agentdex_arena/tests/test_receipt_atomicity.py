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
import logging
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


def _session(sidecar: _StopRecordingSidecar, battle_id: str = "sandbox-deadbeef") -> BattleSession:
    s = BattleSession(
        battle_id=battle_id,
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


def test_finished_session_cache_evicts_old_receipts_but_keeps_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "1")
    gateway = _gateway(tmp_path)
    live = _session(_StopRecordingSidecar())
    live.battle_id = "sandbox-live"
    gateway._publish_session(live.battle_id, live)

    first = _session(_StopRecordingSidecar())
    first.battle_id = "sandbox-first"
    second = _session(_StopRecordingSidecar())
    second.battle_id = "sandbox-second"
    gateway._publish_session(first.battle_id, first)
    gateway._publish_session(second.battle_id, second)

    asyncio.run(gateway._finish(first, {"winner": "Bot", "turns": 4, "inputLog": ["a"]}))
    asyncio.run(gateway._finish(second, {"winner": "Bot", "turns": 5, "inputLog": ["b"]}))

    assert live.battle_id in gateway.sessions  # live sessions are never cache-evicted
    assert first.battle_id not in gateway.sessions
    assert second.battle_id in gateway.sessions
    assert gateway.load_replay(first.battle_id) is not None


def test_replay_cache_is_bounded_and_rehydrates_evicted_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARENA_MAX_REPLAY_CACHE", "1")
    gateway = _gateway(tmp_path)
    first = _session(_StopRecordingSidecar())
    first.battle_id = "sandbox-replay-first"
    second = _session(_StopRecordingSidecar())
    second.battle_id = "sandbox-replay-second"

    asyncio.run(gateway._finish(first, {"winner": "Bot", "turns": 4, "inputLog": ["a"]}))
    asyncio.run(gateway._finish(second, {"winner": "Bot", "turns": 5, "inputLog": ["b"]}))

    assert first.battle_id not in gateway.replays
    assert second.battle_id in gateway.replays

    rehydrated = gateway.load_replay(first.battle_id)
    assert rehydrated is not None
    assert rehydrated["input_log"] == ["a"]
    assert first.battle_id in gateway.replays
    assert second.battle_id not in gateway.replays


def test_backgrounded_finish_failure_is_logged(tmp_path: Path, caplog) -> None:
    """PR #291 review 3435604694: when a /choose is cancelled and the shielded
    _finish later fails, the done-callback retrieves the exception (to avoid
    asyncio's bare "Task exception was never retrieved" warning) — but must LOG
    it, because on the cancellation path no one else does, so a failed
    terminal-receipt commit would otherwise be invisible server-side."""
    gateway = _gateway(tmp_path)
    visitor, opponent = "LogFailBot", "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})
    session = BattleSession(
        battle_id="rated-logfail",
        claims_token_id="tenant-x",
        visitor_name=visitor,
        lane="rated",
        opponent=opponent,
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type]
        opponent_policy=None,
        visitor_choices=["move 1", "move 2"],
    )
    end = {"winner": visitor, "turns": 12, "inputLog": ["a", "b"]}

    gate, release = asyncio.Event(), asyncio.Event()

    async def failing_append(items, *, sidecar=None, battle_id=None, session=None):
        gate.set()
        await release.wait()
        raise OSError("disk full committing the receipt")

    gateway._append_many_or_fail_closed = failing_append  # type: ignore[method-assign]

    async def run() -> None:
        task = asyncio.create_task(
            gateway._advance(session, {"end": dict(end)}, visitor_choice=None)
        )
        await gate.wait()  # the shielded finish is inside the (about-to-fail) append
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task  # the /choose request is cancelled — nobody will retrieve the failure
        with caplog.at_level(logging.ERROR):
            release.set()
            for _ in range(200):  # let the background finish fail + the callback log
                if session.finish_task is None:
                    break
                await asyncio.sleep(0.01)
        assert session.finish_task is None
        assert any("rated-logfail" in r.getMessage() for r in caplog.records), (
            "a backgrounded finish failure on the cancelled path must be logged"
        )

    asyncio.run(run())


def test_post_commit_rating_readback_failure_degrades_receipt_visibly(
    tmp_path: Path, monkeypatch
) -> None:
    """ADX-P0-001 residual: the rated `after` rating readback runs AFTER the
    terminal group durably committed. If it raises, the finish must NOT 500
    (falsely implying nothing happened, leaving session.ended None for a
    stale-expiry forfeit to append a contradictory duplicate group). Instead the
    receipt publishes with a VISIBLY degraded rating block, and the log carries
    exactly one battle_end + one period row."""
    gateway = _gateway(tmp_path)
    visitor, opponent = "DegradeBot", "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})
    session = BattleSession(
        battle_id="rated-degrade",
        claims_token_id="tenant-degrade",
        visitor_name=visitor,
        lane="rated",
        opponent=opponent,
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type]
        opponent_policy=None,
        p1_team="visitor-team",
        p2_team="opponent-team",
        visitor_choices=["move 1", "move 2"],
    )

    from agentdex_arena import gateway as gateway_mod

    real_recompute = gateway_mod.recompute_ladder
    calls = {"n": 0}

    def flaky_recompute(path):
        calls["n"] += 1
        if calls["n"] == 2:  # 1 = the `before` snapshot; 2 = the post-commit readback
            raise OSError("mock post-commit ladder read failure")
        return real_recompute(path)

    monkeypatch.setattr("agentdex_arena.gateway.recompute_ladder", flaky_recompute)

    receipt = asyncio.run(
        gateway._finish(
            session, {"winner": visitor, "turns": 9, "inputLog": ["a", "b"], "keyLines": []}
        )
    )

    # The receipt PUBLISHED (no 500) and degrades visibly, not silently.
    assert session.ended is receipt
    assert receipt["rating"]["published_delta"] == "UNAVAILABLE"
    assert receipt["rating"]["rating"] is None
    assert "durable commit" in receipt["rating"]["note"]
    # Seed disclosure (the rated contract) survives the degradation.
    assert receipt["rating"]["seed_disclosure"] == [1, 2, 3, 4]
    # Exactly ONE terminal group in the log — no duplicate.
    types = [e["type"] for e in gateway.events.iter_events()]
    assert types.count("battle_end") == 1
    assert types.count("period") == 1
    # The battle is terminal: a later stale-expiry appends nothing.
    session.last_touch = 0.0
    asyncio.run(gateway._expire_if_stale(session))
    types_after = [e["type"] for e in gateway.events.iter_events()]
    assert types_after == types


def test_finish_reentry_after_commit_recovers_receipt_without_duplicate_rows(
    tmp_path: Path, monkeypatch
) -> None:
    """ADX-P0-001 residual: if _finish raises AFTER the durable commit but BEFORE
    publishing (session.committed=True, session.ended=None), a re-entered finish
    (the stale-expiry forfeit path) must not append a second, contradictory
    battle_end group. It recovers the receipt from the DURABLE row — the real
    winner, not the retry's forfeit args — and marks it receipt_recovered."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)  # sandbox vs brock, visitor "Bot"

    orig_cache_replay = gateway._cache_replay

    def boom(battle_id: str, replay: dict) -> None:
        raise RuntimeError("mock publish-phase failure")

    monkeypatch.setattr(gateway, "_cache_replay", boom)
    with pytest.raises(RuntimeError, match="mock publish-phase failure"):
        asyncio.run(
            gateway._finish(
                session, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []}
            )
        )

    # The commit landed; the publish did not.
    assert session.committed is True
    assert session.ended is None
    types = [e["type"] for e in gateway.events.iter_events()]
    assert types.count("battle_end") == 1

    # Re-enter with CONTRADICTORY forfeit args (the stale-expiry shape).
    monkeypatch.setattr(gateway, "_cache_replay", orig_cache_replay)
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )

    # Recovered from the durable row: the REAL winner, visibly marked.
    assert receipt["receipt_recovered"] is True
    assert receipt["winner"] == "Bot"
    assert receipt["you_won"] is True
    assert session.ended is receipt
    # Nothing was re-appended — still exactly one terminal group.
    types_after = [e["type"] for e in gateway.events.iter_events()]
    assert types_after.count("battle_end") == 1
    assert types_after == types


# ---- post-commit recovery receipt must be FAITHFUL to the durable group (#650 review) ----


def _commit_then_fail_publish(gateway, session, end, monkeypatch):
    """Run the real _finish through its durable commit, then make the publish
    phase (_cache_replay) raise — leaving session.committed=True, ended=None
    with the full durable group on the log. Returns nothing; the caller then
    re-enters _finish to exercise the recovery path."""
    orig = gateway._cache_replay

    def boom(battle_id: str, replay: dict) -> None:
        raise RuntimeError("mock publish-phase failure")

    monkeypatch.setattr(gateway, "_cache_replay", boom)
    with pytest.raises(RuntimeError, match="mock publish-phase failure"):
        asyncio.run(gateway._finish(session, end))
    assert session.committed is True and session.ended is None
    monkeypatch.setattr(gateway, "_cache_replay", orig)  # restore for the recovery call


def test_recovered_receipt_keeps_the_sandbox_badge(tmp_path: Path, monkeypatch) -> None:
    """#650 review: the durable group commits a `badge` row alongside battle_end
    on a sandbox gym win. The recovery path must surface it — a receipt that
    drops badge_awarded contradicts the committed log."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = BattleSession(
        battle_id="sandbox-badge",
        claims_token_id="tenant-badge",
        visitor_name="Bot",
        lane="sandbox",
        opponent="gym-stall",  # a gym leader -> Stall Badge on a win
        seed=[1, 7, 7, 7],
        sidecar=sidecar,  # type: ignore[arg-type]
        opponent_policy=None,
    )
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    types = [e["type"] for e in gateway.events.iter_events()]
    assert types.count("badge") == 1  # the committed group has the badge row

    receipt = asyncio.run(
        gateway._finish(
            session, {"winner": "gym-stall", "turns": 3, "inputLog": [], "keyLines": []}
        )
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["badge_awarded"] == "Stall Badge"  # recovered from the durable badge row
    assert [e["type"] for e in gateway.events.iter_events()].count("badge") == 1  # no re-append


def test_recovered_receipt_keeps_quarantine(tmp_path: Path, monkeypatch) -> None:
    """#650 review: a quarantined result commits a `quarantine` row in the same
    group. The recovery path must surface quarantined/quarantine_reason."""
    from agentdex_arena.gateway import _QUARANTINE_PUBLIC_REASON

    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)  # sandbox vs brock (no badge)
    # Force the collusion check to fire so the durable group carries a quarantine row.
    monkeypatch.setattr(gateway, "_check_collusion", lambda s, t: "mirror-match no-op detected")

    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    assert [e["type"] for e in gateway.events.iter_events()].count("quarantine") == 1

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["quarantined"] is True
    assert receipt["quarantine_reason"] == _QUARANTINE_PUBLIC_REASON  # opaque, not the detail
    assert receipt["quarantine_reason"] != "mirror-match no-op detected"


def test_recovered_receipt_does_not_advertise_an_unpublished_replay(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: if the post-commit failure struck in _cache_replay, the replay
    was never cached or written, so load_replay() 404s. The recovered receipt must
    NOT promise /replay for a battle whose replay is gone — /fork and /dispute would
    all fail against that receipt."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    assert gateway.load_replay(session.battle_id) is None  # replay genuinely absent

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["replay"] is None  # not a 404-bound URL
    assert "replay_unavailable" in receipt


def test_recovered_receipt_advertises_a_replay_that_IS_backed(tmp_path: Path, monkeypatch) -> None:
    """Companion to the above: when the replay DID get cached before the
    post-commit failure — e.g. _cache_replay populated self.replays on its
    first line, then raised in the limit/evict tail, leaving session.ended
    None — the recovered receipt correctly still advertises /replay. (An
    artifact-write failure cannot reach recovery: that write runs AFTER
    session.ended is set and is swallowed by try/except, so it never leaves
    the committed && ended-None state.)"""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    # Simulate the replay having been durably published (the failure was elsewhere/later).
    gateway._cache_replay(
        session.battle_id, {"input_log": ["x"], "winner": "Bot", "lane": "sandbox"}
    )
    assert gateway.load_replay(session.battle_id) is not None

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["replay"] == f"/replay/{session.battle_id}"
    assert "replay_unavailable" not in receipt


def test_recovered_receipt_runs_publish_cleanup_and_reclaims_frames(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: the recovery path must run the same publish cleanup as the
    normal path — otherwise a recovered finish leaks its live frame buffer and
    never evicts the finished session. On the no-viewer path frames clear now."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    session.frames = [{"seq": 1, "turn": 1, "raw_lines": ["|move|"]}]  # a resident buffer
    session.live_viewers = 0

    receipt = asyncio.run(
        gateway._finish(
            session,
            {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []},
            defer_frame_evict=False,
        )
    )
    assert receipt["receipt_recovered"] is True
    assert session.frames == []  # buffer reclaimed, not leaked


def test_stale_expiry_does_not_mislabel_a_recovered_win_as_forfeit(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: the FULL stale-expiry path. _finish recovers a real committed
    WIN, then _expire_if_stale must NOT stamp forfeit:'turn budget exceeded' on it
    — else the client sees you_won:true AND a timeout forfeit (contradiction)."""
    gateway = _gateway(tmp_path)
    sidecar = _StopRecordingSidecar()
    session = _session(sidecar)  # sandbox, visitor "Bot"
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    # Drive the real stale-expiry: it calls _finish (which recovers) then labels.
    session.last_touch = 0.0
    asyncio.run(gateway._expire_if_stale(session))

    assert session.ended is not None
    assert session.ended["receipt_recovered"] is True
    assert session.ended["you_won"] is True
    assert "forfeit" not in session.ended  # NOT mislabeled a timeout forfeit
    # And still no duplicate terminal group.
    assert [e["type"] for e in gateway.events.iter_events()].count("battle_end") == 1


def test_recovered_rated_receipt_carries_a_degraded_rating_block(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: a rated battle's committed group has a `period` row that
    already moved the ladder. The recovered receipt surfaces the current rating
    but reports published_delta as UNAVAILABLE (the pre-battle snapshot is lost),
    rather than being blind to the ladder movement or inventing a delta."""
    gateway = _gateway(tmp_path)
    visitor, opponent = "RatedBot", "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})
    sidecar = _StopRecordingSidecar()
    session = BattleSession(
        battle_id="rated-recover",
        claims_token_id="tenant-r",
        visitor_name=visitor,
        lane="rated",
        opponent=opponent,
        seed=[1, 2, 3, 4],
        sidecar=sidecar,  # type: ignore[arg-type]
        opponent_policy=None,
        p1_team="vt",
        p2_team="ot",
        visitor_choices=["move 1"],
    )
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": visitor, "turns": 5, "inputLog": ["a", "b"], "keyLines": []},
        monkeypatch,
    )
    assert [e["type"] for e in gateway.events.iter_events()].count("period") == 1

    receipt = asyncio.run(
        gateway._finish(session, {"winner": opponent, "turns": 5, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["winner"] == visitor  # the committed truth, not the retry's forfeit
    assert receipt["rating"]["published_delta"] == "UNAVAILABLE"
    assert receipt["rating"]["seed_disclosure"] == [1, 2, 3, 4]
    assert "the ladder includes this battle" in receipt["rating"]["note"]  # not quarantined
    assert [e["type"] for e in gateway.events.iter_events()].count("period") == 1  # no re-append


def test_recovered_receipt_evicts_finished_session_and_keeps_live(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review (test-fidelity): the recovery path must run the SECOND half of
    the publish cleanup too — move_to_end + _evict_finished_sessions. The frames
    test only covers the buffer clear; this covers eviction. With the finished-
    session cache at 0, a REPLAYABLE recovered session must be evicted (its
    receipt survives via the durable replay) while a live sibling survives.
    (An UNREPLAYABLE recovered session is pinned instead — see the next test.)"""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "0")
    gateway = _gateway(tmp_path)
    live = _session(_StopRecordingSidecar())
    live.battle_id = "sandbox-live"
    gateway._publish_session(live.battle_id, live)  # a live (ended is None) sibling
    session = _session(_StopRecordingSidecar())  # sandbox-deadbeef
    gateway._publish_session(session.battle_id, session)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    # Make the replay backed so this recovered session is evictable (has a durable
    # fallback) — the point here is that eviction (cleanup half-b) RUNS.
    gateway._cache_replay(
        session.battle_id, {"input_log": ["x"], "winner": "Bot", "lane": "sandbox"}
    )

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["replay"] is not None  # backed -> evictable
    assert session.battle_id not in gateway.sessions  # finished recovered session evicted
    assert live.battle_id in gateway.sessions  # the live session survives


def test_unreplayable_recovered_receipt_is_pinned_not_evicted(tmp_path: Path, monkeypatch) -> None:
    """#654 review: an unreplayable recovered receipt (replay is None — no durable
    replay to rehydrate from) is the ONLY copy of the result. Evicting it would
    make the receipt unreachable on every surface. It must be PINNED in the
    session cache even under maximum cache pressure, so /state can still serve
    it."""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "0")
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    gateway._publish_session(session.battle_id, session)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    assert gateway.load_replay(session.battle_id) is None  # replay genuinely gone

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["replay"] is None  # unreplayable
    # Pinned despite cache limit 0 (the recovery-path _evict call + a later one).
    assert session.battle_id in gateway.sessions
    gateway._evict_finished_sessions()  # a later finish's cleanup must not evict it either
    assert session.battle_id in gateway.sessions


def _pin_one(gateway: ArenaGateway, battle_id: str, monkeypatch) -> BattleSession:
    """Drive one session all the way to an UNREPLAYABLE recovered receipt (pinned)."""
    session = _session(_StopRecordingSidecar(), battle_id=battle_id)
    gateway._publish_session(battle_id, session)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True and receipt["replay"] is None
    return session


def test_pinned_receipts_have_their_own_ceiling(tmp_path: Path, monkeypatch, caplog) -> None:
    """The pin must not silently make finished-session memory unbounded. Pins are
    exempt from ARENA_MAX_FINISHED_SESSION_CACHE but obey their OWN ceiling
    (ARENA_MAX_PINNED_RECEIPT_CACHE), dropping oldest-first and logging at error
    level — dropping a pin is the one eviction that truly loses a receipt."""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "0")
    monkeypatch.setenv("ARENA_MAX_PINNED_RECEIPT_CACHE", "2")
    gateway = _gateway(tmp_path)

    oldest = _pin_one(gateway, "sandbox-pin-1", monkeypatch)
    middle = _pin_one(gateway, "sandbox-pin-2", monkeypatch)
    # Two pins, ceiling 2 -> both retained even though the finished cache is 0.
    assert {oldest.battle_id, middle.battle_id} <= set(gateway.sessions)

    with caplog.at_level(logging.ERROR):
        newest = _pin_one(gateway, "sandbox-pin-3", monkeypatch)

    # Third pin pushes past the ceiling -> the OLDEST pin is dropped, not the newest.
    assert oldest.battle_id not in gateway.sessions
    assert middle.battle_id in gateway.sessions
    assert newest.battle_id in gateway.sessions
    # The drop is operator-visible (a receipt was genuinely lost).
    assert any(
        "dropped an unreplayable recovered receipt" in r.message and oldest.battle_id in r.message
        for r in caplog.records
    )


def test_pinned_receipt_is_never_dropped_to_make_room_for_a_replayable_one(
    tmp_path: Path, monkeypatch
) -> None:
    """Pins are evicted ONLY against their own ceiling. A crowd of replayable
    finished sessions must never displace a pin — the replayable ones have a durable
    replay to fall back on; the pin is the only copy of its receipt."""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "1")
    monkeypatch.setenv("ARENA_MAX_PINNED_RECEIPT_CACHE", "1")
    gateway = _gateway(tmp_path)

    pinned = _pin_one(gateway, "sandbox-pin-only", monkeypatch)
    for i in range(5):
        replayable = _session(_StopRecordingSidecar(), battle_id=f"sandbox-replayable-{i}")
        gateway._publish_session(replayable.battle_id, replayable)
        asyncio.run(
            gateway._finish(
                replayable, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []}
            )
        )

    assert pinned.battle_id in gateway.sessions  # survived the crowd
    finished_replayable = [
        b
        for b, s in gateway.sessions.items()
        if s.ended is not None and s.ended.get("replay") is not None
    ]
    assert len(finished_replayable) == 1  # the replayable ones obey their own limit


# ---- the receipt must not promise a replay the durable record cannot back ----


def _break_artifact_write(gateway: ArenaGateway, monkeypatch) -> None:
    """Make the best-effort replay/inputlog artifact write fail (e.g. ENOSPC)."""
    real = Path.write_text

    def boom(self, *a, **kw):  # noqa: ANN001
        if self.name.endswith((".replay.json", ".inputlog.json")):
            raise OSError(28, "No space left on device")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", boom)


def test_receipt_does_not_promise_a_replay_the_artifact_write_could_not_persist(
    tmp_path: Path, monkeypatch
) -> None:
    """The normal publish path used to set `replay: /replay/<id>` UNCONDITIONALLY,
    even when the best-effort artifact write failed. `self.replays` is in-memory and
    LRU-bounded, so once that entry is evicted `/replay` 404s for a receipt that
    promised it — exactly the self-contradicting-receipt class #650 closed for the
    recovery path. Advertise the replay only when the durable write succeeded."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    _break_artifact_write(gateway, monkeypatch)

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []})
    )
    assert receipt["replay"] is None  # not promised
    assert "replay_unavailable" in receipt
    assert "receipt_recovered" not in receipt  # this is the NORMAL path, not recovery
    # And the durable artifact really is absent, so the promise would have 404'd.
    assert not (tmp_path / "arena" / f"{session.battle_id}.replay.json").exists()


def test_receipt_promises_the_replay_when_the_artifact_write_succeeds(tmp_path: Path) -> None:
    """Control: the happy path still advertises the replay and writes the artifact."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []})
    )
    assert receipt["replay"] == f"/replay/{session.battle_id}"
    assert "replay_unavailable" not in receipt
    assert (tmp_path / "arena" / f"{session.battle_id}.replay.json").exists()


def test_unreplayable_normal_receipt_is_pinned_not_evicted(tmp_path: Path, monkeypatch) -> None:
    """A normal finish whose artifact write failed has no durable fallback either —
    the in-memory session is the only copy. It must be pinned like the recovered
    one, so /state can still serve it. The pin keys on the published fact
    (`replay is None`), not on `receipt_recovered`."""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "0")
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    gateway._publish_session(session.battle_id, session)
    _break_artifact_write(gateway, monkeypatch)

    receipt = asyncio.run(
        gateway._finish(session, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []})
    )
    assert receipt["replay"] is None
    assert session.battle_id in gateway.sessions  # pinned despite cache limit 0
    gateway._evict_finished_sessions()
    assert session.battle_id in gateway.sessions


def test_ended_fatal_session_is_not_pinned(tmp_path: Path, monkeypatch) -> None:
    """Key-presence is load-bearing. An ended-FATAL receipt carries NO `replay` key
    (it never promised one, and nothing durable backs it), so `.get("replay") is
    None` would wrongly pin it forever. It must stay evictable."""
    monkeypatch.setenv("ARENA_MAX_FINISHED_SESSION_CACHE", "0")
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    gateway._publish_session(session.battle_id, session)

    def boom(*a, **kw):  # noqa: ANN001
        raise RuntimeError("event log write failed")

    monkeypatch.setattr(gateway.events, "append_many", boom)
    with pytest.raises(HTTPException):
        asyncio.run(
            gateway._finish(
                session, {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []}
            )
        )
    assert session.ended is not None and "replay" not in session.ended  # fatal shape
    gateway._evict_finished_sessions()
    assert session.battle_id not in gateway.sessions  # evictable, not pinned


def test_recovered_rated_quarantined_note_does_not_claim_ladder_inclusion(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: a rated battle can be BOTH on a period row AND quarantined
    (collusion fired). Quarantined battles are excluded from the ladder, so the
    recovered rating-block note must NOT say 'the ladder includes this battle' on
    a receipt that also sets quarantined:true (self-contradiction)."""
    gateway = _gateway(tmp_path)
    visitor, opponent = "QRatedBot", "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})
    session = BattleSession(
        battle_id="rated-quar",
        claims_token_id="tenant-q",
        visitor_name=visitor,
        lane="rated",
        opponent=opponent,
        seed=[1, 2, 3, 4],
        sidecar=_StopRecordingSidecar(),  # type: ignore[arg-type]
        opponent_policy=None,
        p1_team="vt",
        p2_team="ot",
        visitor_choices=["move 1"],
    )
    monkeypatch.setattr(gateway, "_check_collusion", lambda s, t: "low-entropy identical choices")
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": visitor, "turns": 5, "inputLog": ["a", "b"], "keyLines": []},
        monkeypatch,
    )
    # The committed group carries BOTH a period and a quarantine row.
    types = [e["type"] for e in gateway.events.iter_events()]
    assert types.count("period") == 1 and types.count("quarantine") == 1

    receipt = asyncio.run(
        gateway._finish(session, {"winner": opponent, "turns": 5, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["quarantined"] is True
    # The note must be consistent with quarantined:true — NOT claim ladder inclusion.
    assert "quarantined and excluded from the ladder" in receipt["rating"]["note"]
    assert "the ladder includes this battle" not in receipt["rating"]["note"]


def test_recovered_rated_receipt_degrades_when_recovery_readback_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """#650 review: cover the recovery-path rating-readback EXCEPT branch —
    recompute_ladder raising during recovery must degrade the rating block
    visibly (rating None, published_delta UNAVAILABLE), not crash the recovery."""
    gateway = _gateway(tmp_path)
    visitor, opponent = "FailRatedBot", "anchor-max_damage"
    gateway.events.append_many(
        [
            ("register", {"name": visitor, "frozen": False}),
            ("register", {"name": opponent, "frozen": True}),
        ]
    )
    gateway._registered.update({visitor, opponent})
    session = BattleSession(
        battle_id="rated-recover-fail",
        claims_token_id="tenant-rf",
        visitor_name=visitor,
        lane="rated",
        opponent=opponent,
        seed=[1, 2, 3, 4],
        sidecar=_StopRecordingSidecar(),  # type: ignore[arg-type]
        opponent_policy=None,
        p1_team="vt",
        p2_team="ot",
        visitor_choices=["move 1"],
    )
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": visitor, "turns": 5, "inputLog": ["a", "b"], "keyLines": []},
        monkeypatch,
    )
    # Now break recompute_ladder for the recovery readback only (period already committed).
    monkeypatch.setattr(
        "agentdex_arena.gateway.recompute_ladder",
        lambda path: (_ for _ in ()).throw(OSError("mock recovery ladder read failure")),
    )
    receipt = asyncio.run(
        gateway._finish(session, {"winner": opponent, "turns": 5, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["rating"]["rating"] is None
    assert receipt["rating"]["published_delta"] == "UNAVAILABLE"
    assert "readback failed" in receipt["rating"]["note"]


def test_recovered_receipt_preserves_fork_lineage(tmp_path: Path, monkeypatch) -> None:
    """#650 review: cover the recovery fork-lineage copy — a forked session's
    parent_battle_id / fork_turn must survive recovery (the normal receipt carries
    them too)."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    session.parent = ("parent-battle", 4)
    _commit_then_fail_publish(
        gateway,
        session,
        {"winner": "Bot", "turns": 3, "inputLog": ["x"], "keyLines": []},
        monkeypatch,
    )
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 3, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["parent_battle_id"] == "parent-battle"
    assert receipt["fork_turn"] == 4


# ---- durable forfeit marker: recovered timeouts keep their label (#654 review) ----


def test_forfeit_reason_is_durable_in_the_battle_end_row_and_receipt(tmp_path: Path) -> None:
    """A forfeit finish records its reason DURABLY in the battle_end row (not just
    stamped on the in-memory receipt), and the normal receipt surfaces it. This is
    what lets the recovery path restore it (next test)."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    receipt = asyncio.run(
        gateway._finish(
            session,
            {
                "winner": "brock",
                "turns": 4,
                "inputLog": [],
                "keyLines": [],
                "forfeit": "turn budget exceeded",
            },
        )
    )
    assert receipt["forfeit"] == "turn budget exceeded"
    assert receipt["you_won"] is False
    # Durable: the battle_end row carries the marker.
    row = next(
        e["payload"]
        for e in gateway.events.iter_events()
        if e["type"] == "battle_end" and e["payload"]["battle_id"] == session.battle_id
    )
    assert row["forfeit"] == "turn budget exceeded"


def test_non_forfeit_finish_has_no_forfeit_field(tmp_path: Path) -> None:
    """A normal (non-forfeit) finish writes NO forfeit field — durable row or
    receipt — so recovery can trust the marker's absence."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "Bot", "turns": 4, "inputLog": ["x"], "keyLines": []})
    )
    assert "forfeit" not in receipt
    row = next(
        e["payload"]
        for e in gateway.events.iter_events()
        if e["type"] == "battle_end" and e["payload"]["battle_id"] == session.battle_id
    )
    assert "forfeit" not in row


def test_recovered_timeout_keeps_its_forfeit_label(tmp_path: Path, monkeypatch) -> None:
    """#654 review: when the stale-timeout finish ITSELF commits then fails to
    publish, recovery restores the committed timeout receipt — and it must keep the
    'turn budget exceeded' label (from the durable row), so a client polling /state
    after a recovered timeout still sees WHY it lost, exactly like a normal timeout."""
    gateway = _gateway(tmp_path)
    session = _session(_StopRecordingSidecar())
    # First finish = the forfeit itself; commit lands, publish (cache_replay) fails.
    _commit_then_fail_publish(
        gateway,
        session,
        {
            "winner": "brock",
            "turns": 4,
            "inputLog": [],
            "keyLines": [],
            "forfeit": "turn budget exceeded",
        },
        monkeypatch,
    )
    # Recovery re-entry.
    receipt = asyncio.run(
        gateway._finish(session, {"winner": "brock", "turns": 4, "inputLog": [], "keyLines": []})
    )
    assert receipt["receipt_recovered"] is True
    assert receipt["you_won"] is False
    assert receipt["forfeit"] == "turn budget exceeded"  # label survived recovery
    # (the recovered-WIN-has-no-spurious-forfeit case is covered by the existing
    # test_stale_expiry_does_not_mislabel_a_recovered_win_as_forfeit, which now
    # passes via the durable marker's ABSENCE rather than the removed in-memory guard.)
