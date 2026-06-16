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
from pathlib import Path

import pytest
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, BattleSession
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
