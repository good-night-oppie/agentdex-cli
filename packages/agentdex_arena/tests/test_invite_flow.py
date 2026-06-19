"""Integration tests for the GA-CORE-1 invite-code registration gate:
POST /admin/mint-invites (operator) + POST /enroll/redeem-invite (session) +
the ARENA_INVITE_REQUIRED beta gate on /enroll/account."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
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
    a test can drive /enroll/confirm and assert on whether an OOB code was sent."""
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


def test_email_oob_redeems_invite_at_confirm(tmp_path, monkeypatch):
    """The documented email-OOB flow is invite-capable: a client passes invite_code
    on /enroll/request, and /enroll/confirm redeems it (binding to the owner the OOB
    code just proved) and mints the consent token. No session-login step needed."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        r = c.post(
            "/enroll/request",
            json={
                "owner": "alice@x.com",
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
                "invite_code": code,
            },
        )
        assert r.status_code == 200 and len(sent) == 1
        oob_code = sent[0][1]
        r = c.post(f"/enroll/confirm/{oob_code}")
        assert r.status_code == 200 and "token" in r.json()
        # the invite was consumed and the verified owner is admitted
        assert gw.invites.is_admitted("alice@x.com") is True
        assert gw.invites.redeemable(code) is False


def test_email_oob_confirm_requires_a_valid_invite(tmp_path, monkeypatch):
    """Under invite-mode, confirming an OOB enrollment that carried NO (or a bad)
    invite code is rejected at the authoritative mint — no consent token, no
    bypass. The request itself stays uniform (200 + code sent)."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/request",
            json={"owner": "mallory@x.com", "agent_name": "garchomp", "agent_pubkey_hex": _PUBKEY},
        )
        assert r.status_code == 200 and len(sent) == 1  # uniform: code IS sent
        oob_code = sent[0][1]
        r = c.post(f"/enroll/confirm/{oob_code}")
        assert r.status_code == 403  # no valid invite → no consent token minted
        assert gw.invites.is_admitted("mallory@x.com") is False


def test_email_oob_request_is_uniform_no_enumeration(tmp_path, monkeypatch):
    """An unauthenticated /enroll/request must NOT reveal whether an owner is
    admitted: an admitted owner and an un-admitted owner get the byte-identical
    pending response, and both have a code sent (PR #362 review — no admitted-set
    enumeration via this endpoint)."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        c.post(
            "/enroll/redeem-invite", json={"invite_code": code}, headers=_sess(gw, "alice@x.com")
        )
        admitted = c.post(
            "/enroll/request",
            json={"owner": "alice@x.com", "agent_name": "a1", "agent_pubkey_hex": _PUBKEY},
        )
        unadmitted = c.post(
            "/enroll/request",
            json={"owner": "nobody@x.com", "agent_name": "a2", "agent_pubkey_hex": _PUBKEY},
        )
        assert admitted.status_code == unadmitted.status_code == 200
        assert admitted.json() == unadmitted.json()  # indistinguishable response
        # both owners had an OOB code sent (no admission-dependent behavior)
        assert {o for o, _ in sent} == {"alice@x.com", "nobody@x.com"}


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


def test_admin_invites_listing(tmp_path):
    """Operators can audit which seats are redeemed without reading events.jsonl —
    GET /admin/invites returns stats + per-code {code_hash, redeemed_by}, never the
    plaintext code. Operator-only (403 without the admin token)."""
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        codes = c.post("/admin/mint-invites", json={"count": 3}, headers=_admin()).json()["codes"]
        c.post(
            "/enroll/redeem-invite",
            json={"invite_code": codes[0]},
            headers=_sess(gw, "alice@x.com"),
        )
        assert c.get("/admin/invites").status_code == 403  # operator-only
        r = c.get("/admin/invites", headers=_admin())
        assert r.status_code == 200
        body = r.json()
        assert body["stats"] == {"minted": 3, "redeemed": 1, "remaining": 2}
        assert len(body["invites"]) == 3
        redeemed = [i for i in body["invites"] if i["redeemed_by"] is not None]
        assert len(redeemed) == 1 and redeemed[0]["redeemed_by"] == "alice@x.com"
        for code in codes:  # the plaintext codes never appear in the listing (only hashes)
            assert code not in r.text


def test_mint_is_atomic_no_burn_on_append_failure(tmp_path, monkeypatch):
    """The batch mint is ATOMIC (append_many: tmp + fsync + os.replace), so an
    append failure commits NOTHING — there is no partial-commit window that could
    burn seats (durably minted but undistributable). PR #360 + #365 review."""
    gw = _gateway(tmp_path)

    def boom(_items):
        raise OSError("disk full")

    monkeypatch.setattr(gw.events, "append_many", boom)
    with pytest.raises(OSError):
        gw.mint_invites(5, actor_hash="op")
    assert gw.invites.stats()["minted"] == 0  # atomic: nothing committed, no burn


def test_mint_commits_whole_batch(tmp_path):
    """The happy path commits every code in one atomic batch (append_many)."""
    gw = _gateway(tmp_path)
    codes = gw.mint_invites(5, actor_hash="op")
    assert len(codes) == 5
    for c in codes:
        assert gw.invites.redeemable(c) is True
    assert gw.invites.stats()["minted"] == 5


def test_blank_invite_code_is_opaque_403_not_500(tmp_path, monkeypatch):
    """A whitespace-only invite_code passes the request model (min_length=1) but has
    no valid hash; it must surface as the opaque invalid/used 403 on BOTH redeem
    seams, never an uncaught 500 from hashing a blank string. PR #363 review."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway_capture(tmp_path)
    with _client(gw) as c:
        # session redeem path
        r = c.post(
            "/enroll/redeem-invite", json={"invite_code": " "}, headers=_sess(gw, "alice@x.com")
        )
        assert r.status_code == 403
        # email-OOB confirm path (blank invite_code carried to confirm)
        c.post(
            "/enroll/request",
            json={
                "owner": "bob@x.com",
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
                "invite_code": " ",
            },
        )
        oob_code = sent[-1][1]
        assert c.post(f"/enroll/confirm/{oob_code}").status_code == 403
