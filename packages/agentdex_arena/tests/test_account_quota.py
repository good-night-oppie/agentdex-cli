"""Tests for the account-scoped quota surface (ADR-0013 D6): GET /account/quota
+ ConsentAuthority.account_quota_report / quota_key_for.

Verifies the frozen response shape, the owner-pooled `battle` vs per-agent
`evolve`/`badge_mint` keying (the load-bearing distinction from ADR-0011 §3b),
default caps + remaining=cap-used, the account->agents join, that quota_key_for
reports against the EXACT key spend_quota debits, and the auth/503 posture."""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_GH_ID = "12345678"
_PUBKEY = "0" * 64


def _claims(owner: str, agent_name: str) -> ConsentClaims:
    return ConsentClaims(
        token_id="tok12345",
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex=_PUBKEY,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=0.0,
        expires_at=9_999_999_999.0,
        confirmed_via="test",
    )


# ---- authority: key delegation + report ----


def test_quota_key_for_matches_quota_key():
    """The raw-args key MUST equal the claims-derived key byte-for-byte, else the
    D6 read reports against a different bucket than spend_quota debits."""
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    c = _claims(_OWNER, "oppie")
    for scope in ("battle", "evolve", "badge_mint"):
        assert auth.quota_key_for(c.owner, c.agent_name, scope=scope) == auth.quota_key(
            c, scope=scope
        )


def test_report_default_caps_and_full_remaining_when_unspent():
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    rep = auth.account_quota_report(_OWNER, ["oppie"])
    assert rep["battle"] == {"remaining": 5, "cap": 5}
    assert rep["agents"]["oppie"]["evolve"] == {"remaining": 2, "cap": 2}
    assert rep["agents"]["oppie"]["badge_mint"] == {"remaining": 4 + 1, "cap": 5}
    assert rep["utc_day"] == auth.current_utc_day()


def test_report_snapshots_utc_day_once_across_midnight():
    ticks = iter([86_399.0, 86_400.0, 86_400.0, 86_400.0])
    auth = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        now=lambda: next(ticks),
    )
    auth.quota_used["oppie:evolve:19700101"] = 1

    rep = auth.account_quota_report(_OWNER, ["oppie"])

    assert rep["utc_day"] == "19700101"
    assert rep["agents"]["oppie"]["evolve"] == {"remaining": 1, "cap": 2}


def test_report_uses_enrolled_token_quota_caps():
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    rep = auth.account_quota_report(
        _OWNER,
        ["oppie"],
        agent_quotas={"oppie": {"battle": 4, "evolve": 1, "badge_mint": 3}},
    )

    assert rep["battle"] == {"remaining": 4, "cap": 4}
    assert rep["agents"]["oppie"]["evolve"] == {"remaining": 1, "cap": 1}
    assert rep["agents"]["oppie"]["badge_mint"] == {"remaining": 3, "cap": 3}


def test_battle_is_owner_pooled_across_agents():
    """Spending battle (keyed on owner) decrements the single account-level
    battle counter, no matter which agent spent it."""
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    auth.spend_quota(_claims(_OWNER, "oppie"), scope="battle")
    auth.spend_quota(_claims(_OWNER, "scout"), scope="battle")  # different agent, same owner
    rep = auth.account_quota_report(_OWNER, ["oppie", "scout"])
    assert rep["battle"] == {"remaining": 3, "cap": 5}  # 5 - 2


def test_evolve_is_per_agent():
    """evolve is keyed on agent_name — spending for one agent must not touch the
    other's budget."""
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    auth.spend_quota(_claims(_OWNER, "oppie"), scope="evolve")
    rep = auth.account_quota_report(_OWNER, ["oppie", "scout"])
    assert rep["agents"]["oppie"]["evolve"] == {"remaining": 1, "cap": 2}
    assert rep["agents"]["scout"]["evolve"] == {"remaining": 2, "cap": 2}


def test_report_empty_agents_when_none_enrolled():
    auth = ConsentAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    rep = auth.account_quota_report(_OWNER, [])
    assert rep["agents"] == {}
    assert rep["battle"]["cap"] == 5


# ---- endpoint ----


def _gateway(tmp_path: Path, *, with_session=True) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    session = (
        SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
        if with_session
        else None
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=session,
    )


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def test_endpoint_returns_frozen_shape_with_account_agents(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie", quotas={"battle": 4, "evolve": 1, "badge_mint": 3})
    tok = gw.session_auth.mint_session(_OWNER, _GH_ID)
    with _client(gw) as c:
        r = c.get("/account/quota", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"utc_day", "battle", "agents"}
    assert body["battle"] == {"remaining": 4, "cap": 4}
    assert set(body["agents"]) == {"oppie"}
    assert set(body["agents"]["oppie"]) == {"evolve", "badge_mint"}
    assert body["agents"]["oppie"]["evolve"] == {"remaining": 1, "cap": 1}
    assert body["agents"]["oppie"]["badge_mint"] == {"remaining": 3, "cap": 3}


def test_endpoint_reflects_spent_battle(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.authority.spend_quota(_claims(_OWNER, "oppie"), scope="battle")
    tok = gw.session_auth.mint_session(_OWNER, _GH_ID)
    with _client(gw) as c:
        r = c.get("/account/quota", headers={"Authorization": f"Bearer {tok}"})
    assert r.json()["battle"] == {"remaining": 4, "cap": 5}


def test_endpoint_401_without_bearer(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.get("/account/quota").status_code == 401


def test_endpoint_403_on_bad_session(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.get("/account/quota", headers={"Authorization": "Bearer not.valid"})
    assert r.status_code == 403


def test_endpoint_503_when_session_auth_unconfigured(tmp_path):
    gw = _gateway(tmp_path, with_session=False)
    with _client(gw) as c:
        r = c.get("/account/quota", headers={"Authorization": "Bearer whatever"})
    assert r.status_code == 503
