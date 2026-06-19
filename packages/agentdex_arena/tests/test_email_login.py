"""GA-CORE-2 email magic-link login: POST /auth/email/start + /auth/email/verify.

The self-serve HUMAN login that needs NO GitHub OAuth app — ``start`` mails a one-time
code, ``verify`` exchanges it for a SessionAuthority session token (owner = the verified
email). CI-runnable with no PS server / no GitHub: notify_owner is captured in-process.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority, _normalize_owner
from agentdex_arena.gateway import (
    EMAIL_LOGIN_TTL_SEC,
    MAX_PENDING_EMAIL_LOGINS,
    ArenaGateway,
    create_app,
)
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _gateway(tmp_path: Path, *, with_session: bool = True):
    sent: list[tuple[str, str]] = []
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: sent.append((owner, code)),
        session_authority=(
            SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
            if with_session
            else None
        ),
    )
    return gw, sent


def _client(gw: ArenaGateway) -> TestClient:
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def test_email_login_503_when_session_auth_unconfigured(tmp_path):
    gw, _ = _gateway(tmp_path, with_session=False)
    with _client(gw) as c:
        assert c.post("/auth/email/start", json={"email": "a@b.com"}).status_code == 503
        assert c.post("/auth/email/verify", json={"code": "x"}).status_code == 503


def test_email_login_start_then_verify_mints_session(tmp_path):
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post("/auth/email/start", json={"email": "Alice@Oppie.XYZ"})
        assert r.status_code == 200 and r.json()["status"] == "pending_email_verification"
        # the one-time code is delivered to the email, never in the response body
        assert len(sent) == 1 and sent[0][0] == "Alice@Oppie.XYZ"
        assert "code" not in r.json()
        code = sent[0][1]
        r = c.post("/auth/email/verify", json={"code": code})
        assert r.status_code == 200
        body = r.json()
        assert "session_token" in body and body["owner"] == "Alice@Oppie.XYZ"
        # the minted session verifies and carries the email-proof federated identity
        claims = gw.session_auth.verify_session(body["session_token"])
        assert claims.owner == "Alice@Oppie.XYZ"
        assert claims.github_id == f"email:{_normalize_owner('Alice@Oppie.XYZ')}"


def test_email_code_is_one_time(tmp_path):
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        c.post("/auth/email/start", json={"email": "a@b.com"})
        code = sent[0][1]
        assert c.post("/auth/email/verify", json={"code": code}).status_code == 200
        # second use is rejected — the code was popped on the first verify
        assert c.post("/auth/email/verify", json={"code": code}).status_code == 403


def test_unknown_code_is_opaque_403(tmp_path):
    gw, _ = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.post("/auth/email/verify", json={"code": "never-issued"}).status_code == 403


def test_expired_code_is_403(tmp_path):
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        c.post("/auth/email/start", json={"email": "a@b.com"})
        code = sent[0][1]
        email, _exp = gw.pending_email_logins[code]
        gw.pending_email_logins[code] = (email, gw.now() - 1.0)  # force expiry
        assert c.post("/auth/email/verify", json={"code": code}).status_code == 403


def test_malformed_email_is_422(tmp_path):
    gw, _ = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.post("/auth/email/start", json={"email": "{EMAIL}"}).status_code == 422
        assert c.post("/auth/email/start", json={"email": "not-an-email"}).status_code == 422


def test_start_is_uniform_for_any_email(tmp_path):
    """start never reveals whether an email is registered — any email gets the same
    pending response + a delivered code (only the email's owner can read it)."""
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        a = c.post("/auth/email/start", json={"email": "known@x.com"})
        b = c.post("/auth/email/start", json={"email": "stranger@y.com"})
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()  # indistinguishable
        assert {o for o, _ in sent} == {"known@x.com", "stranger@y.com"}


def test_login_code_ttl_is_within_contract(tmp_path):
    """US-1.3 AC1: the one-time code must expire in ≤10 min."""
    assert EMAIL_LOGIN_TTL_SEC <= 600.0
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        c.post("/auth/email/start", json={"email": "a@b.com"})
        code = sent[0][1]
        _email, expires_at = gw.pending_email_logins[code]
        assert expires_at - gw.now() <= 600.0 + 1.0  # issued with a ≤10-min TTL


def test_resend_cooldown_no_duplicate_send(tmp_path):
    """A rapid re-request for the same email is a no-op SEND (delivery-spam guard) —
    same uniform response, but notify_owner fires only once."""
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        r1 = c.post("/auth/email/start", json={"email": "a@b.com"})
        r2 = c.post("/auth/email/start", json={"email": "A@B.com"})  # same normalized owner
        assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert len(sent) == 1  # cooldown suppressed the second delivery
    assert len(gw.pending_email_logins) == 1  # one live code per email


def test_global_cap_rejects_abusive_burst(tmp_path):
    """A cross-email burst beyond the hard cap is rejected (429) rather than growing
    the pending map / spamming the channel unboundedly."""
    gw, sent = _gateway(tmp_path)
    now = gw.now()
    # fill to the cap with distinct, non-expired, far-future codes (no cooldown/dedup hit)
    gw.pending_email_logins = {
        f"code{i}": (f"u{i}@x.com", now + 600.0) for i in range(MAX_PENDING_EMAIL_LOGINS)
    }
    with _client(gw) as c:
        r = c.post("/auth/email/start", json={"email": "overflow@x.com"})
    assert r.status_code == 429
    assert sent == []  # no delivery on the rejected request
