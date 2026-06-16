"""Owner export completeness (ADX-P1-002).

/my/events used to filter only by top-level payload.tenant_id, which silently
dropped two row types the owner actually owns:
  - `badge` events carried only agent_name + badge + battle_id — so a tenant
    pull missed every earned badge receipt (PASS 41).
  - `period` rows carry their battle ids INSIDE a nested events[] list, with
    no top-level tenant_id — so a tenant pull missed every rating-period
    receipt for their own rated battles.

This pins both fixes: the badge event now carries tenant_id, AND /my/events
returns owner-belonging rows even when ownership has to be derived from the
nested `events[].battle_id` chain. The agent_name-fallback path is also
covered so a legacy badge row (pre-PR, without tenant_id) is still
recoverable by the owner that earned it.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar, sidecar_available
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def _arena_client(tmp_path: Path):
    signing_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing_key)
    owner_inbox: dict[str, str] = {}
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda o, code: owner_inbox.__setitem__(o, code),
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    return app, gateway, owner_inbox


def _enroll(client, owner_inbox, agent_key, *, owner, name):
    r1 = client.post(
        "/enroll/request",
        json={
            "owner": owner,
            "agent_name": name,
            "agent_pubkey_hex": agent_key.public_key().public_bytes_raw().hex(),
        },
    )
    assert r1.status_code == 200
    code = owner_inbox[owner]
    r2 = client.post(f"/enroll/confirm/{code}")
    assert r2.status_code == 200
    return r2.json()["token"]


def test_my_events_includes_badge_with_tenant_id(tmp_path: Path):
    """A newly appended badge row (carrying tenant_id per the fix) is returned
    by /my/events without any agent_name fallback."""
    app, gateway, _ = _arena_client(tmp_path)
    with TestClient(app, raise_server_exceptions=False) as client:
        agent_key = Ed25519PrivateKey.generate()
        token = (
            _enroll(
                client,
                gateway.notify_owner.__self__ if False else None,
                agent_key,
                owner="eddie@oppie.xyz",
                name="BadgeBot",
            )
            if False
            else None
        )  # _enroll uses owner_inbox via app fixture; rebuild inline
    # rebuild client cleanly (owner_inbox lives in closure of the fixture above)
    app, gateway, owner_inbox = _arena_client(tmp_path / "x")
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, owner_inbox, agent_key, owner="eddie@oppie.xyz", name="BadgeBot")
        claims = gateway.authority.verify(token, scope="battle")
        # Directly append a badge row matching the post-PR payload shape
        # (tenant_id + agent_name + battle + timestamp).
        gateway.events.append(
            "badge",
            {
                "tenant_id": claims.token_id,
                "agent_name": claims.agent_name,
                "badge": "Boulder Badge",
                "battle_id": "sandbox-abcd1234ab",
                "timestamp": time.time(),
            },
        )
        r = client.post("/my/events", json={"token": token, "since_seq": -1})
        assert r.status_code == 200, r.text
        types = [e["type"] for e in r.json()["events"]]
        assert "badge" in types, f"badge missing from owner export: {types}"


def test_my_events_includes_legacy_badge_via_agent_name(tmp_path: Path):
    """A pre-PR `badge` row (no tenant_id, just agent_name) is still recoverable
    by the owner that earned it — the agent_name fallback path."""
    app, gateway, owner_inbox = _arena_client(tmp_path)
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, owner_inbox, agent_key, owner="eddie@oppie.xyz", name="LegacyBot")
        # Legacy payload shape — NO tenant_id, just agent_name + badge + battle.
        gateway.events.append(
            "badge",
            {
                "agent_name": "LegacyBot",
                "badge": "Cascade Badge",
                "battle_id": "sandbox-feedface00",
                "timestamp": time.time(),
            },
        )
        r = client.post("/my/events", json={"token": token, "since_seq": -1})
        assert r.status_code == 200, r.text
        rows = r.json()["events"]
        assert any(
            e["type"] == "badge" and e["payload"].get("badge") == "Cascade Badge" for e in rows
        ), f"legacy badge missing from owner export: {[(e['type'], e['payload']) for e in rows]}"


def test_my_events_does_not_leak_other_owners_legacy_badge(tmp_path: Path):
    """The agent_name fallback uses the verified ConsentClaims agent_name, so a
    legacy badge with someone else's agent_name MUST NOT leak to this caller."""
    app, gateway, owner_inbox = _arena_client(tmp_path)
    key_a = Ed25519PrivateKey.generate()
    key_b = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token_a = _enroll(client, owner_inbox, key_a, owner="alice@oppie.xyz", name="AliceBot")
        _ = _enroll(client, owner_inbox, key_b, owner="bob@oppie.xyz", name="BobBot")
        # Legacy badge for Bob — Alice's pull MUST NOT include it.
        gateway.events.append(
            "badge",
            {
                "agent_name": "BobBot",
                "badge": "Thunder Badge",
                "battle_id": "sandbox-bobsbid01",
                "timestamp": time.time(),
            },
        )
        r = client.post("/my/events", json={"token": token_a, "since_seq": -1})
        assert r.status_code == 200, r.text
        rows = r.json()["events"]
        assert not any(e["type"] == "badge" for e in rows), (
            f"Alice's export leaked Bob's badge: {[(e['type'], e['payload']) for e in rows]}"
        )


def test_my_events_includes_period_via_nested_battle_id(tmp_path: Path):
    """A rated `period` row has no top-level tenant_id — only nested
    `events[].battle_id`. The owner's earlier battle_begin/end fixed the
    battle_id → tenant mapping; /my/events must follow that link."""
    app, gateway, owner_inbox = _arena_client(tmp_path)
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, owner_inbox, agent_key, owner="eddie@oppie.xyz", name="RatedBot")
        claims = gateway.authority.verify(token, scope="battle")
        battle_id = "rated-deadbeef00"
        # Establish ownership: a battle_begin/end pair with the tenant_id.
        gateway.events.append(
            "battle_begin",
            {
                "tenant_id": claims.token_id,
                "battle_id": battle_id,
                "lane": "rated",
                "visitor": "RatedBot",
                "opponent": "anchor-max_damage",
            },
        )
        gateway.events.append(
            "battle_end",
            {
                "tenant_id": claims.token_id,
                "battle_id": battle_id,
                "lane": "rated",
                "winner": "RatedBot",
                "turns": 12,
                "input_log_blake2b16": "0" * 32,
            },
        )
        # Now the period row — NO top-level tenant_id; only nested battle_id.
        gateway.events.append(
            "period",
            {
                "events": [
                    {
                        "battle_id": battle_id,
                        "p1": "RatedBot",
                        "p2": "anchor-max_damage",
                        "winner": "RatedBot",
                        "input_log_blake2b16": "0" * 32,
                    }
                ]
            },
        )
        r = client.post("/my/events", json={"token": token, "since_seq": -1})
        assert r.status_code == 200, r.text
        types = [e["type"] for e in r.json()["events"]]
        assert "period" in types, f"period missing from owner export: {types}"
        # And the battle_begin/end SHOULD be there too (they always were).
        assert "battle_begin" in types and "battle_end" in types
