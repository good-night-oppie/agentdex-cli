"""GA-AUTH dual-mode session cookie + double-submit CSRF (ADX-Online Track A).

Invariants (the security floor):
  * CLI/agent (Authorization: Bearer) keeps working unchanged + is CSRF-exempt.
  * Browser (?web=1) gets the session in an HttpOnly cookie; the token is stripped
    from the body; a readable arena_csrf cookie is issued.
  * A cookie-authed STATE-CHANGING request without a matching X-CSRF-Token is 403.
"""

from __future__ import annotations

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_PUBKEY = (
    "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret
)


def _gw(tmp_path):
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
    )


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _session(gw, owner=_OWNER):
    return gw.session_auth.mint_session(owner, f"email:{owner}")


def _setcookie(resp, name):
    for line in resp.headers.get_list("set-cookie"):
        if line.startswith(f"{name}="):
            return line.lower()
    return None


# ---- /auth/email/verify dual-mode delivery ----


def test_email_verify_cli_returns_token_in_body_no_cookie(tmp_path):
    gw = _gw(tmp_path)
    gw.email_login_start(_OWNER)
    code = next(iter(gw.pending_email_logins))
    r = _client(gw).post("/auth/email/verify", json={"code": code})
    assert r.status_code == 200, r.text
    assert "session_token" in r.json()  # CLI byte-identical
    assert "set-cookie" not in {k.lower() for k in r.headers}  # no cookie for the CLI


def test_email_verify_web_sets_httponly_cookie_and_strips_token(tmp_path):
    gw = _gw(tmp_path)
    gw.email_login_start(_OWNER)
    code = next(iter(gw.pending_email_logins))
    r = _client(gw).post("/auth/email/verify?web=1", json={"code": code})
    assert r.status_code == 200, r.text
    assert "session_token" not in r.json()  # stripped from body (XSS mitigation)
    sess = _setcookie(r, "arena_session")
    csrf = _setcookie(r, "arena_csrf")
    assert sess and "httponly" in sess and "secure" in sess and "samesite=lax" in sess
    assert csrf and "secure" in csrf and "httponly" not in csrf  # csrf must be JS-readable


def test_auth_csrf_route_issues_readable_cookie(tmp_path):
    r = _client(_gw(tmp_path)).get("/auth/csrf")
    assert r.status_code == 200
    csrf = _setcookie(r, "arena_csrf")
    assert csrf and "secure" in csrf and "httponly" not in csrf


# ---- /enroll/account dual-mode auth + CSRF fork ----


def test_enroll_cli_bearer_no_csrf_ok(tmp_path):
    gw = _gw(tmp_path)
    tok = _session(gw)
    r = _client(gw).post(
        "/enroll/account",
        headers={"Authorization": f"Bearer {tok}"},
        json={"agent_name": "cli-bot", "agent_pubkey_hex": _PUBKEY, "agent_source": "openai/codex"},
    )
    assert r.status_code == 200, r.text  # CLI is CSRF-exempt


def test_enroll_cookie_without_csrf_is_403(tmp_path):
    gw = _gw(tmp_path)
    tok = _session(gw)
    r = _client(gw).post(
        "/enroll/account",
        cookies={"arena_session": tok},
        json={"agent_name": "web-bot", "agent_pubkey_hex": _PUBKEY, "agent_source": "openai/codex"},
    )
    assert r.status_code == 403  # cookie-authed state-change without CSRF → blocked


def test_enroll_cookie_with_matching_csrf_ok(tmp_path):
    gw = _gw(tmp_path)
    tok = _session(gw)
    r = _client(gw).post(
        "/enroll/account",
        cookies={"arena_session": tok, "arena_csrf": "csrf-abc"},
        headers={"X-CSRF-Token": "csrf-abc"},
        json={
            "agent_name": "web-bot2",
            "agent_pubkey_hex": _PUBKEY,
            "agent_source": "openai/codex",
        },
    )
    assert r.status_code == 200, r.text  # double-submit match → allowed


def test_enroll_cookie_with_mismatched_csrf_is_403(tmp_path):
    gw = _gw(tmp_path)
    tok = _session(gw)
    r = _client(gw).post(
        "/enroll/account",
        cookies={"arena_session": tok, "arena_csrf": "cookie-val"},
        headers={"X-CSRF-Token": "different-val"},
        json={
            "agent_name": "web-bot3",
            "agent_pubkey_hex": _PUBKEY,
            "agent_source": "openai/codex",
        },
    )
    assert r.status_code == 403  # cookie != header → CSRF fail


def test_enroll_no_auth_is_401(tmp_path):
    r = _client(_gw(tmp_path)).post(
        "/enroll/account",
        json={"agent_name": "x", "agent_pubkey_hex": _PUBKEY, "agent_source": "openai/codex"},
    )
    assert r.status_code == 401
