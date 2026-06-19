"""Integration tests for the GA-CORE-1 invite-code registration gate:
POST /admin/mint-invites (operator) + POST /enroll/redeem-invite (session) +
the ARENA_INVITE_REQUIRED beta gate on /enroll/account."""

from __future__ import annotations

import hashlib
from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_ADMIN_TOKEN = "operator-secret-token"  # pragma: allowlist secret
_ADMIN_HASH = hashlib.sha256(_ADMIN_TOKEN.encode()).hexdigest()
_PUBKEY = (
    "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret
)


def _gateway(tmp_path: Path) -> ArenaGateway:
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
    )


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _sess(gw, owner="alice@x.com", gh="111"):
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, gh)}"}


def _admin():
    return {"X-Admin-Token": _ADMIN_TOKEN}


def test_mint_invites_requires_admin(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.post("/admin/mint-invites", json={"count": 3}).status_code == 403
        assert (
            c.post(
                "/admin/mint-invites", json={"count": 3}, headers={"X-Admin-Token": "wrong"}
            ).status_code
            == 403
        )


def test_mint_then_redeem_then_enroll(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        # operator mints 5 codes
        r = c.post("/admin/mint-invites", json={"count": 5}, headers=_admin())
        assert r.status_code == 200
        codes = r.json()["codes"]
        assert len(codes) == 5 and r.json()["stats"]["minted"] == 5

        # un-invited owner cannot enroll (beta gate)
        r = c.post(
            "/enroll/account",
            json={"agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
            headers=_sess(gw),
        )
        assert r.status_code == 403

        # redeem an invite → admitted
        r = c.post("/enroll/redeem-invite", json={"invite_code": codes[0]}, headers=_sess(gw))
        assert r.status_code == 200 and r.json()["admitted"] is True

        # now enroll works
        r = c.post(
            "/enroll/account",
            json={"agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
            headers=_sess(gw),
        )
        assert r.status_code == 200


def test_invite_code_is_single_use(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        assert (
            c.post(
                "/enroll/redeem-invite",
                json={"invite_code": code},
                headers=_sess(gw, "alice@x.com"),
            ).status_code
            == 200
        )
        # a different owner cannot reuse it
        r = c.post(
            "/enroll/redeem-invite",
            json={"invite_code": code},
            headers=_sess(gw, "bob@x.com", "222"),
        )
        assert r.status_code == 403


def test_unknown_code_is_opaque_403(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post("/enroll/redeem-invite", json={"invite_code": "never-minted"}, headers=_sess(gw))
        assert r.status_code == 403


def test_reredeem_is_idempotent_no_code_burned(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        codes = c.post("/admin/mint-invites", json={"count": 2}, headers=_admin()).json()["codes"]
        assert (
            c.post(
                "/enroll/redeem-invite", json={"invite_code": codes[0]}, headers=_sess(gw)
            ).status_code
            == 200
        )
        # same owner redeems again (e.g. new session) — no-op, second code untouched
        assert (
            c.post(
                "/enroll/redeem-invite", json={"invite_code": codes[1]}, headers=_sess(gw)
            ).status_code
            == 200
        )
        assert gw.invites.redeemable(codes[1]) is True
        assert gw.invites.stats()["redeemed"] == 1


def test_gate_off_by_default_existing_enroll_unaffected(tmp_path):
    """Without ARENA_INVITE_REQUIRED, enroll is open (existing behavior)."""
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
            headers=_sess(gw),
        )
        assert r.status_code == 200  # not gated when the flag is off


def test_redemption_survives_restart_via_replay(tmp_path):
    """invite_grant + invite_redeem events rehydrate admission on a fresh gateway."""
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        c.post(
            "/enroll/redeem-invite", json={"invite_code": code}, headers=_sess(gw, "alice@x.com")
        )
    # a fresh gateway replays the same events file
    gw2 = ArenaGateway(
        authority=gw.authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena2",
        notify_owner=lambda owner, code: None,
        session_authority=gw.session_auth,
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
    )
    assert gw2.invites.is_admitted("alice@x.com") is True
    assert gw2.invites.redeemable(code) is False
