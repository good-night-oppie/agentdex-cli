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


def _gateway_capture(tmp_path: Path):
    """A gateway whose notify_owner records every (owner, code) it would send, so
    a test can both drive /enroll/confirm and assert NO code was sent on a
    fail-fast rejection."""
    sent: list[tuple[str, str]] = []
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: sent.append((owner, code)),
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
    )
    return gw, sent


def test_email_oob_request_is_invite_gated_and_sends_no_code(tmp_path, monkeypatch):
    """The legacy email-OOB path also mints a consent token (at /enroll/confirm),
    so it must be invite-gated too — else ARENA_INVITE_REQUIRED is bypassable by
    self-serving through request→confirm. An un-admitted owner is rejected BEFORE
    any OOB code is generated/sent."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/request",
            json={
                "owner": "mallory@x.com",
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
            },
        )
        assert r.status_code == 403
        assert sent == []  # fail-fast: no OOB code ever sent to an un-invited owner


def test_email_oob_path_works_for_admitted_owner(tmp_path, monkeypatch):
    """An owner who has redeemed an invite can still use the email-OOB path."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
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
        r = c.post(
            "/enroll/request",
            json={"owner": "alice@x.com", "agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
        )
        assert r.status_code == 200
        assert len(sent) == 1 and sent[0][0] == "alice@x.com"
        oob_code = sent[0][1]
        r = c.post(f"/enroll/confirm/{oob_code}")
        assert r.status_code == 200 and "token" in r.json()


def test_email_oob_confirm_gated_when_flag_flips_after_pending(tmp_path, monkeypatch):
    """Defense-in-depth: a flag flipped ON after an enrollment was already pending
    must still be blocked at the authoritative mint (enroll_confirm), and the
    rejected confirm must NOT consume the pending code (peek-not-pop)."""
    monkeypatch.delenv("ARENA_INVITE_REQUIRED", raising=False)
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        # flag OFF at request time → pending created + code sent
        r = c.post(
            "/enroll/request",
            json={"owner": "alice@x.com", "agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
        )
        assert r.status_code == 200 and len(sent) == 1
        oob_code = sent[0][1]
        # operator flips the beta gate ON before the human confirms
        monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
        # confirm now 403s (owner not admitted) and the pending code is NOT consumed
        assert c.post(f"/enroll/confirm/{oob_code}").status_code == 403
        # admit the owner, then the SAME pending code confirms
        admit = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][
            0
        ]
        assert (
            c.post(
                "/enroll/redeem-invite",
                json={"invite_code": admit},
                headers=_sess(gw, "alice@x.com"),
            ).status_code
            == 200
        )
        r = c.post(f"/enroll/confirm/{oob_code}")
        assert r.status_code == 200 and "token" in r.json()


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


def test_invite_codes_are_hashed_in_event_log(tmp_path):
    """The plaintext invite code is a bearer secret (an unredeemed code = a
    claimable beta seat), so ONLY sha256(code) is written to the durable log —
    on BOTH the mint (invite_grant) and the redeem (invite_redeem)."""
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        c.post(
            "/enroll/redeem-invite", json={"invite_code": code}, headers=_sess(gw, "alice@x.com")
        )
    raw = (tmp_path / "events.jsonl").read_text()
    assert code not in raw  # the plaintext code never lands in the durable log
    assert hashlib.sha256(code.encode()).hexdigest() in raw  # only its hash does


def test_legacy_plaintext_code_event_replays(tmp_path):
    """Migration-safe: an invite_grant/invite_redeem written in the pre-hashing
    schema (plaintext ``code``) still rehydrates — replay hashes the legacy code so
    the in-memory slot matches what a freshly-hashed redeem would look up."""
    gw = _gateway(tmp_path)
    gw.events.append("invite_grant", {"code": "legacy-1", "actor_hash": "op"})
    gw.events.append("invite_redeem", {"code": "legacy-1", "owner": "alice@x.com"})
    # a fresh gateway replays the legacy-format events file
    gw2 = ArenaGateway(
        authority=gw.authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena2",
        notify_owner=lambda owner, code: None,
        session_authority=gw.session_auth,
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
    )
    assert gw2.invites.is_admitted("alice@x.com") is True
    assert gw2.invites.redeemable("legacy-1") is False  # plaintext lookup hashes + matches
