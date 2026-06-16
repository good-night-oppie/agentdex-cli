"""Class B quota — spend-after-success (ADX-P1-001).

`spend_quota` runs AFTER the fallible work succeeds, not before — so
platform / validation / signer failures cannot burn a user's daily slot.
Sites covered: rated battle_begin (PASS 35/36 P1), badge_mint (PASS 34 P2),
and /evolution/request (PASS 33 P2).

These tests pin the per-site contract directly: each fallible-step failure
returns the expected error code AND leaves the daily quota intact.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar, sidecar_available
from agentdex_arena.badge_auth import BadgeAuthority
from agentdex_arena.consent import ConsentAuthority, _normalize_owner
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


# The kanban-pinned illegal team (same as test_visitor_surface.py) — Koraidon
# is Uber-tagged in gen9ou so the begin path 422s, the canonical PASS 35 case.
ILLEGAL_TEAM = (
    "Koraidon||Leftovers|OrichalcumPulse|FlareBlitz,CollisionCourse,DrainPunch,"
    "SwordsDance|Jolly|,252,,,,252|||||,,,,,Fire"
)


def _battle_used(gateway: ArenaGateway, owner: str) -> int:
    """Read the rated-battle quota counter directly (per-owner per-day per ADR-0011 §3a)."""
    day = time.strftime("%Y%m%d", time.gmtime(gateway.now()))
    key = f"{_normalize_owner(owner)}:battle:{day}"
    return gateway.authority.quota_used.get(key, 0)


def _scope_used(gateway: ArenaGateway, agent_name: str, scope: str) -> int:
    day = time.strftime("%Y%m%d", time.gmtime(gateway.now()))
    key = f"{agent_name}:{scope}:{day}"
    return gateway.authority.quota_used.get(key, 0)


def _arena_client(tmp_path: Path, *, badge_signing_key_hex: str | None = None):
    signing_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing_key)
    owner_inbox: dict[str, str] = {}
    badge_auth = (
        BadgeAuthority(signing_key_hex=badge_signing_key_hex) if badge_signing_key_hex else None
    )
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda o, code: owner_inbox.__setitem__(o, code),
        badge_authority=badge_auth,
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    return app, gateway, owner_inbox


def _enroll(client, owner_inbox, agent_key, *, owner="eddie@oppie.xyz", name="QuotaBot"):
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


def test_invalid_team_does_not_burn_rated_quota(tmp_path: Path):
    """PASS 35: a 422 invalid-team rejection on a rated begin must NOT spend
    a daily slot — the user can retry with a valid team and still have all 5."""
    app, gateway, owner_inbox = _arena_client(tmp_path)
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, owner_inbox, agent_key, name="InvalidTeamBot")
        start = client.post("/battle/start", json={"token": token}).json()
        sig = agent_key.sign(start["pop_challenge"].encode()).hex()
        r = client.post(
            "/battle/begin",
            json={
                "token": token,
                "battle_nonce": start["battle_nonce"],
                "pop_signature_hex": sig,
                "lane": "rated",
                "team": ILLEGAL_TEAM,
            },
        )
        assert r.status_code == 422, r.text
        assert _battle_used(gateway, "eddie@oppie.xyz") == 0


def test_publication_paused_does_not_burn_rated_quota(tmp_path: Path):
    """PASS 36 (variant): instrument-red kill-switch (publication_allowed=False)
    is an operator outage — it must NOT spend the user's slot."""
    app, gateway, owner_inbox = _arena_client(tmp_path)
    gateway._publication_allowed_override = False  # operator-side kill-switch
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, owner_inbox, agent_key, name="PausedBot")
        start = client.post("/battle/start", json={"token": token}).json()
        sig = agent_key.sign(start["pop_challenge"].encode()).hex()
        r = client.post(
            "/battle/begin",
            json={
                "token": token,
                "battle_nonce": start["battle_nonce"],
                "pop_signature_hex": sig,
                "lane": "rated",
            },
        )
        assert r.status_code == 403, r.text
        assert _battle_used(gateway, "eddie@oppie.xyz") == 0


def test_badge_signer_outage_does_not_burn_quota(tmp_path: Path):
    """PASS 34: a 503 sign_badge failure (signer outage) must NOT spend the
    daily badge_mint slot. Achieved by monkeypatching badge_auth.sign_badge
    to throw BadgeAuthError."""
    from agentdex_arena.badge_auth import BadgeAuthError

    badge_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    app, gateway, owner_inbox = _arena_client(tmp_path, badge_signing_key_hex=badge_key)
    # Grant membership so badge_mint passes the paid-feature gate.
    gateway.authority.grant_membership("eddie@oppie.xyz", time.time() + 86400)

    def boom(payload):
        raise BadgeAuthError("mock signer outage")

    gateway.badge_auth.sign_badge = boom  # type: ignore[method-assign]

    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        # Enrollment defaults grant the `badge_mint` scope (ADR-0011 11c).
        token = _enroll(client, owner_inbox, agent_key, name="SignerOutageBot")
        r = client.post("/badge/mint", json={"token": token})
        assert r.status_code == 503, r.text
        assert _scope_used(gateway, "SignerOutageBot", "badge_mint") == 0


def test_evolve_sidecar_error_does_not_burn_quota(tmp_path: Path):
    """PASS 33: a sidecar / infra failure inside offer_seeds must NOT spend
    the daily evolve slot."""
    import agentdex_arena.gateway as gw_mod

    async def boom(*_args, **_kwargs):
        raise RuntimeError("mock offer_seeds infra fail")

    app, gateway, owner_inbox = _arena_client(tmp_path)
    # Patch on the module the route imports (`from agentdex_arena.offered_seeds
    # import offer_seeds`); we patch the SOURCE module so the local import
    # inside the route picks up the boom version.
    import agentdex_arena.offered_seeds as seeds_mod

    original = seeds_mod.offer_seeds
    seeds_mod.offer_seeds = boom  # type: ignore[assignment]
    agent_key = Ed25519PrivateKey.generate()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            token = _enroll(client, owner_inbox, agent_key, name="EvolveOutageBot")
            r = client.post("/evolution/request", json={"token": token, "reasoning": "test"})
            assert r.status_code == 400, r.text
            assert _scope_used(gateway, "EvolveOutageBot", "evolve") == 0
    finally:
        seeds_mod.offer_seeds = original
        # silence unused-import linter; we re-import gw_mod elsewhere
        _ = gw_mod
