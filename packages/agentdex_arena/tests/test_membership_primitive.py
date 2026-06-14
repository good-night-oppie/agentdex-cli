"""Integration test suite for the membership primitive (ADR-0011 11b.4).

Builds on 11b.1 (AdminAuthority unit tests) + 11b.2 (ConsentAuthority membership
unit tests) + 11b.3 (handler smoke test). This file covers the cross-cutting
end-to-end invariants: event replay across restart, EventLog hygiene under
failed admin attempts, owner normalization end-to-end, audit-log payload shape,
and the SKILL.md-absent-admin constraint.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority, ConsentError
from agentdex_arena.gateway import ArenaGateway, create_app

_ADMIN_TOKEN = "integration-suite-admin-token"  # noqa: S105 — fixture, not a real secret
_ADMIN_HASH = hashlib.sha256(_ADMIN_TOKEN.encode()).hexdigest()
_NOW = 1_700_000_000.0


def _make_gateway(tmp_path: Path, *, admin: AdminAuthority | None = None) -> ArenaGateway:
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    auth = ConsentAuthority(signing_key_hex=signing, now=lambda: _NOW)
    return ArenaGateway(
        authority=auth,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        admin_authority=admin or AdminAuthority(token_hash_hex=_ADMIN_HASH),
        now=lambda: _NOW,
    )


def _client(gateway: ArenaGateway):
    app = create_app(gateway, sidecar_factory=Sidecar)
    return TestClient(app, raise_server_exceptions=False)


def _auth_headers() -> dict[str, str]:
    return {"X-Admin-Token": _ADMIN_TOKEN}


def _grant(client, owner: str, valid_until: float, headers=None) -> object:
    return client.post(
        "/admin/grant-membership",
        json={"owner": owner, "valid_until_epoch": valid_until},
        headers=headers if headers is not None else _auth_headers(),
    )


# ---- replay across restart ----


def test_membership_grant_survives_gateway_restart(tmp_path):
    """Grant via the route; tear down + reconstruct gateway; authority.memberships
    must be re-hydrated from the EventLog and verify_membership must pass."""
    gw1 = _make_gateway(tmp_path)
    with _client(gw1) as c:
        r = _grant(c, "Eddie@Oppie.XYZ", _NOW + 86_400)
        assert r.status_code == 200, r.text

    # New gateway from same events_path -> replay must hydrate
    gw2 = _make_gateway(tmp_path)
    assert "eddie@oppie.xyz" in gw2.authority.memberships
    assert gw2.authority.memberships["eddie@oppie.xyz"] == _NOW + 86_400


def test_replay_skips_malformed_membership_grant_events(tmp_path):
    """A hand-crafted malformed event must NOT crash boot; well-formed events
    after it must still hydrate."""
    gw1 = _make_gateway(tmp_path)
    with _client(gw1) as c:
        _grant(c, "alice@a.com", _NOW + 1000)  # well-formed

    # Append a hand-crafted malformed event
    events_path = tmp_path / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "seq": 9999,
            "type": "membership_grant",
            "payload": {"owner": "", "valid_until_epoch": "not-a-number"},
        }) + "\n")

    # Append another well-formed event AFTER the malformed one
    with _client(gw1) as c:
        _grant(c, "bob@b.com", _NOW + 2000)

    # Reconstruct: boot must succeed, well-formed entries must hydrate
    gw2 = _make_gateway(tmp_path)
    assert "alice@a.com" in gw2.authority.memberships
    assert "bob@b.com" in gw2.authority.memberships
    assert "" not in gw2.authority.memberships  # malformed must be skipped


# ---- EventLog hygiene under failed admin attempts ----


def test_failed_admin_attempts_do_not_bloat_eventlog(tmp_path):
    """100x wrong-bearer requests must not write a single event. Audit lives in
    logs, not the durable EventLog (avoids attacker-driven log amplification)."""
    gw = _make_gateway(tmp_path)
    events_path = tmp_path / "events.jsonl"
    initial_lines = sum(1 for _ in events_path.open()) if events_path.exists() else 0

    with _client(gw) as c:
        for _ in range(100):
            r = _grant(c, "x@y.z", _NOW + 100, headers={"X-Admin-Token": "wrong"})
            assert r.status_code == 403

    final_lines = sum(1 for _ in events_path.open()) if events_path.exists() else 0
    assert final_lines == initial_lines, "no events should be written for failed admin attempts"


def test_missing_admin_header_returns_403_with_no_event_written(tmp_path):
    """Missing header (vs wrong-token) must also return 403 + zero events."""
    gw = _make_gateway(tmp_path)
    events_path = tmp_path / "events.jsonl"
    initial = sum(1 for _ in events_path.open()) if events_path.exists() else 0
    with _client(gw) as c:
        r = _grant(c, "x@y.z", _NOW + 100, headers={})
        assert r.status_code == 403
    final = sum(1 for _ in events_path.open()) if events_path.exists() else 0
    assert final == initial


# ---- owner normalization end-to-end ----


def test_owner_normalization_grant_vs_verify_match_across_case_and_whitespace(tmp_path):
    """Grant under 'Eddie@Oppie.XYZ' → verify_membership for claims with
    'eddie@oppie.xyz' / '  EDDIE@OPPIE.XYZ  ' / 'eddie＠oppie.xyz' (NFKC) all pass."""
    gw = _make_gateway(tmp_path)
    with _client(gw) as c:
        r = _grant(c, "Eddie@Oppie.XYZ", _NOW + 100)
        assert r.status_code == 200
        assert r.json()["owner"] == "eddie@oppie.xyz"

    # Construct claims with various owner casings — verify_membership must match
    from agentdex_arena.consent import ConsentClaims
    for variant in ("eddie@oppie.xyz", "  EDDIE@OPPIE.XYZ  ", "eddie＠oppie.xyz"):
        claims = ConsentClaims(
            token_id="t0001abcd",
            owner=variant,
            agent_name="TestBot",
            agent_pubkey_hex="0" * 64,
            scopes=["enroll", "battle", "evolve"],
            issued_at=_NOW,
            expires_at=_NOW + 86_400,
            confirmed_via="test",
        )
        gw.authority.verify_membership(claims)  # should not raise


# ---- revocation via past epoch ----


def test_revocation_via_past_epoch_through_the_route(tmp_path):
    """Single-code-path revocation: grant + re-grant with valid_until <= now."""
    gw = _make_gateway(tmp_path)
    with _client(gw) as c:
        # Grant active
        r = _grant(c, "alice@x.com", _NOW + 100)
        assert r.status_code == 200

        # Re-grant with past-epoch revokes
        r = _grant(c, "alice@x.com", _NOW - 1)
        assert r.status_code == 200
        assert r.json()["valid_until_epoch"] == _NOW - 1

    # Both events present in EventLog (audit preserved)
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").open()
        if json.loads(line)["type"] == "membership_grant"
    ]
    assert len(events) == 2
    assert events[0]["payload"]["valid_until_epoch"] == _NOW + 100
    assert events[1]["payload"]["valid_until_epoch"] == _NOW - 1

    # verify_membership now fails
    from agentdex_arena.consent import ConsentClaims
    claims = ConsentClaims(
        token_id="t0002abcd",
        owner="alice@x.com",
        agent_name="A",
        agent_pubkey_hex="0" * 64,
        scopes=["battle"],
        issued_at=_NOW,
        expires_at=_NOW + 100,
        confirmed_via="test",
    )
    with pytest.raises(ConsentError, match="membership required"):
        gw.authority.verify_membership(claims)


# ---- audit-log payload shape + plaintext-never-in-events ----


def test_event_payload_shape_and_plaintext_token_never_in_events_file(tmp_path):
    """The membership_grant event payload must include the actor_hash (first 8
    hex chars of the stored admin hash) and the normalized owner. The plaintext
    admin token MUST NOT appear anywhere in events.jsonl bytes."""
    gw = _make_gateway(tmp_path)
    with _client(gw) as c:
        r = _grant(c, "Eddie@Oppie.XYZ", _NOW + 86_400)
        assert r.status_code == 200

    raw_bytes = (tmp_path / "events.jsonl").read_bytes()
    # Plaintext admin token never written
    assert _ADMIN_TOKEN.encode() not in raw_bytes
    # Full hash also not written (only the 8-char prefix)
    assert _ADMIN_HASH.encode() not in raw_bytes

    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").open()
        if json.loads(line).get("type") == "membership_grant"
    ]
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["owner"] == "eddie@oppie.xyz"  # normalized
    assert payload["tenant_id"] == "eddie@oppie.xyz"  # mirrors owner
    assert payload["valid_until_epoch"] == _NOW + 86_400
    assert payload["granted_at"] == _NOW
    # actor_hash present + correct length + matches first-8 of stored hash
    assert payload["actor_hash"] == _ADMIN_HASH[:8]
    assert len(payload["actor_hash"]) == 8


# ---- auth-before-body-validation ordering ----


def test_auth_runs_before_body_parse_so_schema_is_not_leaked(tmp_path):
    """Malformed body + no admin header → 403 (auth fails first), NOT 422
    (which would echo pydantic field expectations to an unauthenticated probe)."""
    gw = _make_gateway(tmp_path)
    with _client(gw) as c:
        for bad_body in (b"{", b"not-json-at-all", b"[]", b""):
            r = c.post("/admin/grant-membership", content=bad_body, headers={})
            assert r.status_code == 403, f"body={bad_body!r} got {r.status_code}"


# ---- SKILL.md absence assertion ----


def test_skill_md_does_not_mention_admin_surface():
    """SKILL.md is the agent-facing doc. Admin endpoints + env var + header
    name MUST NOT appear there — admin surface is operator-only."""
    skill_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "agentdex_arena"
        / "SKILL.md"
    )
    text = skill_path.read_text()
    for forbidden in ("/admin/", "X-Admin-Token", "ARENA_ADMIN_TOKEN_HASH", "grant-membership"):
        assert forbidden not in text, f"SKILL.md must not document {forbidden!r}"


# ---- admin_authority=None fail-safe ----


def test_admin_routes_403_when_admin_authority_is_none(tmp_path):
    """Test-fixture / dev gateway constructed without admin_authority must
    still respond 403 to admin routes (instead of 500 / crash)."""
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    auth = ConsentAuthority(signing_key_hex=signing, now=lambda: _NOW)
    gw = ArenaGateway(
        authority=auth,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda o, c: None,
        admin_authority=None,
        now=lambda: _NOW,
    )
    with _client(gw) as c:
        r = _grant(c, "x@y.z", _NOW + 100)
        assert r.status_code == 403
