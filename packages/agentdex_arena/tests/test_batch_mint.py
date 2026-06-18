"""Tests for the curated-launch batch-mint tool (ENROLL-P0-batch-mint).

Locks the contract that batch-minted tokens are (1) verifiable by the same
ConsentAuthority the live gateway uses, (2) backed by durable register events
(names survive restart), (3) reserved/duplicate-safe, and (4) secret-safe
(tokens to a 0600 file, never stdout).
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from agentdex_arena import batch_mint as bm
from agentdex_arena.consent import ConsentAuthority
from agentdex_engine.modules.arena import EventLog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _key_hex() -> str:
    return Ed25519PrivateKey.generate().private_bytes_raw().hex()


def _pubkey_hex() -> str:
    return Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()


def _authority() -> ConsentAuthority:
    return ConsentAuthority(signing_key_hex=_key_hex())


def _roster(n: int = 2) -> list[dict]:
    return [
        {
            "owner": f"owner{i}@example.com",
            "agent_name": f"agent-{i}",
            "agent_pubkey_hex": _pubkey_hex(),
        }
        for i in range(n)
    ]


def test_batch_mint_tokens_verify_with_battle_scope(tmp_path: Path):
    authority = _authority()
    events = EventLog(tmp_path / "events.jsonl")
    roster = _roster(3)

    results, errors = bm.batch_mint(
        roster, authority=authority, events=events, confirmed_via="batch-mint:test"
    )

    assert errors == []
    assert len(results) == 3
    for r, src in zip(results, roster, strict=True):
        claims = authority.verify(r["token"], scope="battle")  # would raise if invalid
        assert claims.agent_name == src["agent_name"]
        assert claims.owner == src["owner"]
        assert "battle" in claims.scopes
        assert claims.confirmed_via == "batch-mint:test"
        assert r["expires_at"] == claims.expires_at


def test_batch_mint_appends_register_events(tmp_path: Path):
    authority = _authority()
    events = EventLog(tmp_path / "events.jsonl")
    roster = _roster(2)

    bm.batch_mint(roster, authority=authority, events=events, confirmed_via="x")

    # A fresh EventLog over the same file sees the durable register rows.
    reloaded = EventLog(tmp_path / "events.jsonl")
    registered = bm.load_registered(reloaded)
    assert registered == {"agent-0", "agent-1"}


def test_batch_mint_rejects_reserved_name(tmp_path: Path):
    authority = _authority()
    events = EventLog(tmp_path / "events.jsonl")
    roster = [{"owner": "o@e.com", "agent_name": "_house", "agent_pubkey_hex": _pubkey_hex()}]

    with pytest.raises(bm.BatchMintError):
        bm.batch_mint(roster, authority=authority, events=events, confirmed_via="x")


def test_batch_mint_rejects_anchor_prefix(tmp_path: Path):
    authority = _authority()
    events = EventLog(tmp_path / "events.jsonl")
    roster = [{"owner": "o@e.com", "agent_name": "anchor-gpt5", "agent_pubkey_hex": _pubkey_hex()}]

    with pytest.raises(bm.BatchMintError):
        bm.batch_mint(roster, authority=authority, events=events, confirmed_via="x")


def test_batch_mint_skip_errors_collects_and_continues(tmp_path: Path):
    authority = _authority()
    events = EventLog(tmp_path / "events.jsonl")
    pk = _pubkey_hex()
    roster = [
        {"owner": "o@e.com", "agent_name": "good-1", "agent_pubkey_hex": pk},
        {"owner": "o@e.com", "agent_name": "good-1", "agent_pubkey_hex": pk},  # duplicate
        {"owner": "o@e.com", "agent_name": "_ladder", "agent_pubkey_hex": pk},  # reserved
        {"owner": "o@e.com", "agent_name": "good-2", "agent_pubkey_hex": pk},
    ]

    results, errors = bm.batch_mint(
        roster, authority=authority, events=events, confirmed_via="x", skip_errors=True
    )

    assert {r["agent_name"] for r in results} == {"good-1", "good-2"}
    assert len(errors) == 2  # the dup + the reserved


def test_main_writes_0600_file_and_no_token_on_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _key_hex())
    roster_path = tmp_path / "roster.json"
    out_path = tmp_path / "tokens.json"
    roster_path.write_text(json.dumps(_roster(2)), encoding="utf-8")

    rc = bm.main(
        [
            "--roster",
            str(roster_path),
            "--out",
            str(out_path),
            "--runtime-dir",
            str(tmp_path / "runtime"),
            "--confirmed-via",
            "batch-mint:curated",
        ]
    )
    assert rc == 0

    minted = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(minted) == 2
    # 0600 perms (owner-only) — tokens are secrets.
    mode = stat.S_IMODE(out_path.stat().st_mode)
    assert mode == 0o600

    out = capsys.readouterr().out
    assert "2 token(s) written" in out
    # CRITICAL: no token value leaked to stdout.
    for r in minted:
        assert r["token"] not in out


def test_main_overwrites_existing_loose_file_to_0600(tmp_path, monkeypatch):
    """Reusing an --out path that already exists must NOT keep its looser mode.

    The prior os.open(out, O_CREAT, 0o600) ignored the mode for an existing file,
    so writing tokens over a touched/checked-in 0644 placeholder leaked them under
    world-readable perms. The atomic temp+replace write resets the inode to 0600.
    """
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _key_hex())
    roster_path = tmp_path / "roster.json"
    out_path = tmp_path / "tokens.json"
    roster_path.write_text(json.dumps(_roster(1)), encoding="utf-8")

    # Pre-existing world-readable file at the target path (the leak precondition).
    out_path.write_text("stale placeholder", encoding="utf-8")
    out_path.chmod(0o644)
    assert stat.S_IMODE(out_path.stat().st_mode) == 0o644

    rc = bm.main(
        [
            "--roster",
            str(roster_path),
            "--out",
            str(out_path),
            "--runtime-dir",
            str(tmp_path / "rt"),
        ]
    )
    assert rc == 0
    # Overwrite reset the secret file to owner-only.
    assert stat.S_IMODE(out_path.stat().st_mode) == 0o600
    assert len(json.loads(out_path.read_text(encoding="utf-8"))) == 1


def test_main_preflights_unwritable_out_before_registering(tmp_path, monkeypatch, capsys):
    """A bad --out path must abort BEFORE any durable register event is appended.

    Otherwise the names are reserved but the tokens are never delivered, and a
    corrected rerun rejects the roster as duplicates (PR #232 review). Point
    --out under a path that is a file (so its parent dir can't be created) and
    assert the run fails closed with zero durable side effects.
    """
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _key_hex())
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_roster(2)), encoding="utf-8")
    runtime_dir = tmp_path / "rt"

    blocker = tmp_path / "blocker"  # a FILE, so blocker/tokens.json's dir can't exist
    blocker.write_text("i am a file", encoding="utf-8")
    bad_out = blocker / "tokens.json"

    rc = bm.main(
        ["--roster", str(roster_path), "--out", str(bad_out), "--runtime-dir", str(runtime_dir)]
    )
    assert rc == 2
    assert "not writable" in capsys.readouterr().err
    # Zero durable side effects: no register events were appended for any entry.
    events_file = runtime_dir / "events.jsonl"
    if events_file.exists():
        assert bm.load_registered(EventLog(events_file)) == set()


def test_main_fail_closed_without_signing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ARENA_SIGNING_KEY_HEX", raising=False)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_roster(1)), encoding="utf-8")

    rc = bm.main(["--roster", str(roster_path), "--out", str(tmp_path / "out.json")])
    assert rc == 2
    assert "ARENA_SIGNING_KEY_HEX not set" in capsys.readouterr().err
