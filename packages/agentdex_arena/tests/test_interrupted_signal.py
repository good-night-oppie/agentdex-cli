"""Restart-interrupted battles get a clear 409, not an opaque 403 (RECOVER-P1).

In-memory sessions are wiped on boot. A battle the owner began in a prior process
that never ended is "interrupted by a restart" — the gateway rebuilds that set from
the EventLog (begin-minus-end) and /choose returns 409 for the owner (others 403,
preserving D7 anti-enumeration).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_engine.modules.arena import EventLog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _mint(
    authority: ConsentAuthority, *, token_id: str, owner="eddie@oppie.xyz", name="PartnerBot"
) -> str:
    claims = ConsentClaims(
        token_id=token_id,
        owner=owner,
        agent_name=name,
        agent_pubkey_hex=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex(),
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=0.0,
        expires_at=4_102_444_800.0,  # year 2100 — never expired for the test
        confirmed_via="test",
    )
    return authority.mint(claims)


def _seed_begin(events_path: Path, *, battle_id: str, tenant_id: str, ended: bool) -> None:
    log = EventLog(events_path)
    log.append("battle_begin", {"battle_id": battle_id, "tenant_id": tenant_id, "lane": "rated"})
    if ended:
        log.append("battle_end", {"battle_id": battle_id, "tenant_id": tenant_id, "winner": "x"})


def _gateway(tmp_path: Path, key_hex: str) -> ArenaGateway:
    return ArenaGateway(
        authority=ConsentAuthority(signing_key_hex=key_hex),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


def test_boot_replay_tracks_begun_but_not_ended(tmp_path: Path):
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    _seed_begin(tmp_path / "events.jsonl", battle_id="rated-aaa", tenant_id="tok-1", ended=False)
    _seed_begin(tmp_path / "events.jsonl", battle_id="rated-bbb", tenant_id="tok-2", ended=True)
    gw = _gateway(tmp_path, key)
    assert gw._interrupted == {"rated-aaa": "tok-1"}  # ended one is NOT interrupted


def test_choose_returns_409_for_owner_of_interrupted_battle(tmp_path: Path):
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    token_id = uuid.uuid4().hex[:16]
    _seed_begin(tmp_path / "events.jsonl", battle_id="rated-aaa", tenant_id=token_id, ended=False)
    gw = _gateway(tmp_path, key)  # "restart": rebuilds _interrupted from the log
    token = _mint(gw.authority, token_id=token_id)
    app = create_app(gw, sidecar_factory=lambda: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/battle/rated-aaa/choose", json={"token": token, "choice_index": 1})
    assert r.status_code == 409
    assert "interrupted by a gateway restart" in r.text


def test_choose_returns_403_for_non_owner(tmp_path: Path):
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    _seed_begin(
        tmp_path / "events.jsonl",
        battle_id="rated-aaa",
        tenant_id="someone-elses-token",
        ended=False,
    )
    gw = _gateway(tmp_path, key)
    token = _mint(gw.authority, token_id=uuid.uuid4().hex[:16])  # different token_id
    app = create_app(gw, sidecar_factory=lambda: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/battle/rated-aaa/choose", json={"token": token, "choice_index": 1})
    assert r.status_code == 403  # not the owner → opaque, no 'interrupted' leak
    assert "interrupted" not in r.text


def test_choose_returns_403_for_unknown_battle(tmp_path: Path):
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    gw = _gateway(tmp_path, key)  # empty log → nothing interrupted
    token = _mint(gw.authority, token_id=uuid.uuid4().hex[:16])
    app = create_app(gw, sidecar_factory=lambda: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/battle/never-existed/choose", json={"token": token, "choice_index": 1})
    assert r.status_code == 403


def _seed_fork(events_path: Path, *, battle_id: str, tenant_id: str, ended: bool) -> None:
    log = EventLog(events_path)
    log.append(
        "battle_fork",
        {"battle_id": battle_id, "tenant_id": tenant_id, "parent_battle_id": "src", "fork_turn": 3},
    )
    if ended:
        log.append("battle_end", {"battle_id": battle_id, "tenant_id": tenant_id, "winner": "x"})


def test_boot_replay_tracks_forked_battle(tmp_path: Path):
    """A sandbox fork is a live battle too (battle_fork event) — it must join the
    interrupted set so a post-restart touch gets the 409, not a 403 (PR #246 review)."""
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    _seed_fork(
        tmp_path / "events.jsonl", battle_id="sandbox-fork-aaa", tenant_id="tok-f", ended=False
    )
    _seed_fork(
        tmp_path / "events.jsonl", battle_id="sandbox-fork-bbb", tenant_id="tok-f", ended=True
    )
    gw = _gateway(tmp_path, key)
    assert gw._interrupted == {"sandbox-fork-aaa": "tok-f"}  # ended fork removed


def test_state_returns_409_for_owner_of_interrupted_battle(tmp_path: Path):
    """HTTP clients poll /battle/{id}/state before choosing — after a restart that
    must give the owner the 409 signal too, not an opaque 403 (PR #246 review)."""
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    token_id = uuid.uuid4().hex[:16]
    _seed_begin(tmp_path / "events.jsonl", battle_id="rated-aaa", tenant_id=token_id, ended=False)
    gw = _gateway(tmp_path, key)
    token = _mint(gw.authority, token_id=token_id)
    app = create_app(gw, sidecar_factory=lambda: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/battle/rated-aaa/state", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 409
    assert "interrupted by a gateway restart" in r.text


def test_state_returns_403_for_non_owner_of_interrupted_battle(tmp_path: Path):
    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    _seed_begin(
        tmp_path / "events.jsonl", battle_id="rated-aaa", tenant_id="someone-else", ended=False
    )
    gw = _gateway(tmp_path, key)
    token = _mint(gw.authority, token_id=uuid.uuid4().hex[:16])
    app = create_app(gw, sidecar_factory=lambda: None)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/battle/rated-aaa/state", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "interrupted" not in r.text


def test_mcp_choose_signals_interrupted_after_restart(tmp_path: Path):
    """The native MCP choose_action must surface the restart signal too, not an
    ambiguous 'Battle session not found' the agent reads as its own bug (PR #246)."""
    from agentdex_arena import mcp_surface

    key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    token_id = uuid.uuid4().hex[:16]
    _seed_begin(tmp_path / "events.jsonl", battle_id="rated-aaa", tenant_id=token_id, ended=False)
    gw = _gateway(tmp_path, key)
    token = _mint(gw.authority, token_id=token_id)
    cvtoken = mcp_surface.current_gateway.set(gw)
    try:
        with pytest.raises(ValueError, match="interrupted by a gateway restart"):
            asyncio.run(
                mcp_surface.choose_action(token=token, battle_id="rated-aaa", choice_index=1)
            )
    finally:
        mcp_surface.current_gateway.reset(cvtoken)
