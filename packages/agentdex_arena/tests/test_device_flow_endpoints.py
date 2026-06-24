"""Integration tests for the device-flow routes (ADR-0013 D2): /auth/device/start
+ /auth/device/poll, wired through a real ArenaGateway + SessionAuthority + a
GitHubDeviceFlow whose transport is a scripted fake (zero network).

Covers the frozen contract shapes, the full login (start → pending → authorized
→ session token + verified-email owner), the durable account_link write +
account->agents resolution, GitHub-side fault → 502, and the 503-when-
unconfigured posture (no session auth / no device-flow)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.device_flow import (
    GITHUB_ACCESS_TOKEN_URL,
    GITHUB_AUTHORIZE_URL,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_EMAILS_URL,
    GITHUB_USER_URL,
    GitHubDeviceFlow,
)
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_GH_ID = "12345678"
_WEB_PUBLIC_BASE = "https://arena.example"
_WEB_CLIENT_SECRET = "web-oauth-test-value"  # pragma: allowlist secret


class _FakeTransport:
    def __init__(self, scripted):
        self._scripted = {k: list(v) for k, v in scripted.items()}
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        queue = self._scripted.get(url)
        if not queue:
            raise AssertionError(f"unexpected/exhausted call to {url}")
        return queue.pop(0)


def _start_script():
    return {
        GITHUB_DEVICE_CODE_URL: [
            (
                200,
                {
                    "device_code": "dev-abc",
                    "user_code": "WXYZ-7890",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 5,
                    "expires_in": 900,
                },
            )
        ]
    }


def _authorized_script(owner: str = _OWNER):
    return {
        GITHUB_ACCESS_TOKEN_URL: [
            (200, {"error": "authorization_pending"}),  # first poll
            (200, {"access_token": "gho_token"}),  # second poll
        ],
        GITHUB_USER_URL: [(200, {"id": int(_GH_ID), "login": "eddie"})],
        GITHUB_EMAILS_URL: [(200, [{"email": owner, "primary": True, "verified": True}])],
    }


def _setcookie(resp, name):
    for line in resp.headers.get_list("set-cookie"):
        if line.startswith(f"{name}="):
            return line
    return ""


def _cookie_value(resp, name):
    line = _setcookie(resp, name)
    if not line:
        return ""
    return line.split(";", 1)[0].split("=", 1)[1]


def _gateway(
    tmp_path: Path,
    *,
    transport=None,
    with_session=True,
    with_flow=True,
    public_base_url: str = _WEB_PUBLIC_BASE,
    client_secret: str = _WEB_CLIENT_SECRET,
):
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    session = (
        SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
        if with_session
        else None
    )
    flow = (
        GitHubDeviceFlow(
            client_id="Iv1.test",
            client_secret=client_secret,
            transport=transport or (lambda *a: (200, {})),
        )
        if with_flow
        else None
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=session,
        device_flow=flow,
        public_base_url=public_base_url,
    )


def _client(gateway):
    return TestClient(create_app(gateway, sidecar_factory=Sidecar), raise_server_exceptions=False)


# ---- start ----


def test_start_returns_frozen_contract_fields(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport(_start_script()))
    with _client(gw) as c:
        r = c.post("/auth/device/start")
    assert r.status_code == 200
    assert set(r.json()) == {
        "user_code",
        "verification_uri",
        "device_code",
        "interval",
        "expires_in",
    }
    assert r.json()["user_code"] == "WXYZ-7890"


# ---- full login: pending then authorized ----


def test_poll_pending_then_authorized_full_login(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport(_authorized_script()))
    with _client(gw) as c:
        pending = c.post("/auth/device/poll", json={"device_code": "dev-abc"})
        assert pending.status_code == 200
        assert pending.json() == {"status": "pending"}

        done = c.post("/auth/device/poll", json={"device_code": "dev-abc"})
    assert done.status_code == 200
    body = done.json()
    assert set(body) == {"session_token", "owner", "expires_at"}
    assert body["owner"] == _OWNER
    # the returned session token verifies against the gateway's session authority
    claims = gw.session_auth.verify_session(body["session_token"])
    assert claims.owner == _OWNER
    assert claims.github_id == _GH_ID
    assert body["expires_at"] == claims.expires_at


def test_poll_authorized_preserves_existing_github_owner_link(tmp_path):
    original_owner = "old-primary@example.test"
    changed_primary = "new-primary@example.test"
    gw = _gateway(tmp_path, transport=_FakeTransport(_authorized_script(owner=changed_primary)))
    gw.events.append("account_link", {"github_id": _GH_ID, "owner": original_owner})
    gw.accounts.link(_GH_ID, original_owner)

    with _client(gw) as c:
        c.post("/auth/device/poll", json={"device_code": "dev-abc"})  # pending
        done = c.post("/auth/device/poll", json={"device_code": "dev-abc"})

    assert done.status_code == 200
    body = done.json()
    assert body["owner"] == original_owner
    claims = gw.session_auth.verify_session(body["session_token"])
    assert claims.owner == original_owner
    assert gw.accounts.owner_for(_GH_ID) == original_owner
    account_link_events = [e for e in gw.events.iter_events() if e.get("type") == "account_link"]
    assert len(account_link_events) == 1
    assert account_link_events[0]["payload"] == {"github_id": _GH_ID, "owner": original_owner}


# ---- browser OAuth: /auth/github -> /oauth/github ----


def test_browser_github_start_redirects_with_state_and_pkce(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport({}))
    with _client(gw) as c:
        r = c.get("/auth/github", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    parsed = urlparse(loc)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == GITHUB_AUTHORIZE_URL
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["Iv1.test"]
    assert qs["redirect_uri"] == [f"{_WEB_PUBLIC_BASE}/oauth/github"]
    assert qs["scope"] == ["read:user user:email"]
    assert qs["state"] == [_cookie_value(r, "arena_oauth_state")]
    assert qs["code_challenge_method"] == ["S256"]
    assert len(qs["code_challenge"][0]) == 43
    state_cookie = _setcookie(r, "arena_oauth_state").lower()
    pkce_cookie = _setcookie(r, "arena_oauth_pkce").lower()
    return_cookie = _setcookie(r, "arena_oauth_return_to").lower()
    assert "httponly" in state_cookie and "secure" in state_cookie
    assert "httponly" in pkce_cookie and "secure" in pkce_cookie
    assert "httponly" in return_cookie and "secure" in return_cookie


def test_browser_github_callback_mints_web_session_without_returning_tokens(tmp_path):
    transport = _FakeTransport(
        {
            GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
            GITHUB_USER_URL: [(200, {"id": int(_GH_ID), "login": "eddie"})],
            GITHUB_EMAILS_URL: [(200, [{"email": _OWNER, "primary": True, "verified": True}])],
        }
    )
    gw = _gateway(tmp_path, transport=transport)
    with _client(gw) as c:
        start = c.get("/auth/github", follow_redirects=False)
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={"arena_oauth_state": state, "arena_oauth_pkce": verifier},
            follow_redirects=False,
        )
    assert done.status_code == 303, done.text
    assert done.headers["location"] == "/dashboard/"
    assert "arena_session=" in _setcookie(done, "arena_session")
    assert "httponly" in _setcookie(done, "arena_session").lower()
    assert "arena_csrf=" in _setcookie(done, "arena_csrf")
    assert gw.accounts.owner_for(_GH_ID) == _OWNER
    method, url, _headers, body = transport.calls[0]
    assert method == "POST" and url == GITHUB_ACCESS_TOKEN_URL
    assert body["code"] == "abc123"
    assert body["redirect_uri"] == f"{_WEB_PUBLIC_BASE}/oauth/github"
    assert body["code_verifier"] == verifier
    assert body["client_secret"] == _WEB_CLIENT_SECRET


def test_browser_github_start_requires_public_base_url(tmp_path):
    gw = _gateway(tmp_path, public_base_url="")
    with _client(gw) as c:
        status = c.get("/auth/github/status")
        start = c.get("/auth/github", follow_redirects=False)
    assert status.status_code == 503
    assert start.status_code == 503


def test_browser_github_start_requires_client_secret(tmp_path):
    gw = _gateway(tmp_path, client_secret="")
    with _client(gw) as c:
        status = c.get("/auth/github/status")
        start = c.get("/auth/github", follow_redirects=False)
    assert status.status_code == 503
    assert start.status_code == 503


def test_browser_github_callback_missing_secret_fails_before_exchange(tmp_path):
    transport = _FakeTransport(
        {
            GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
        }
    )
    gw = _gateway(tmp_path, transport=transport, client_secret="")
    with _client(gw) as c:
        done = c.get(
            "/oauth/github?code=abc123&state=real",
            cookies={"arena_oauth_state": "real", "arena_oauth_pkce": "verifier"},
            follow_redirects=False,
        )
    assert done.status_code == 503
    assert transport.calls == []


def test_device_start_does_not_require_client_secret(tmp_path):
    gw = _gateway(
        tmp_path,
        transport=_FakeTransport(_start_script()),
        client_secret="",
    )
    with _client(gw) as c:
        device = c.post("/auth/device/start")
        browser = c.get("/auth/github/status")
    assert device.status_code == 200
    assert browser.status_code == 503


def test_browser_github_roundtrip_can_return_to_ga_funnel(tmp_path):
    transport = _FakeTransport(
        {
            GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
            GITHUB_USER_URL: [(200, {"id": int(_GH_ID), "login": "eddie"})],
            GITHUB_EMAILS_URL: [(200, [{"email": _OWNER, "primary": True, "verified": True}])],
        }
    )
    gw = _gateway(tmp_path, transport=transport)
    with _client(gw) as c:
        start = c.get("/auth/github?next=/enroll", follow_redirects=False)
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        return_to = _cookie_value(start, "arena_oauth_return_to")
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={
                "arena_oauth_state": state,
                "arena_oauth_pkce": verifier,
                "arena_oauth_return_to": return_to,
            },
            follow_redirects=False,
        )
    assert done.status_code == 303, done.text
    assert done.headers["location"] == "/enroll"
    assert _setcookie(done, "arena_oauth_return_to").lower().startswith('arena_oauth_return_to=""')


def _github_transport(owner: str = _OWNER) -> _FakeTransport:
    return _FakeTransport(
        {
            GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
            GITHUB_USER_URL: [(200, {"id": int(_GH_ID), "login": "eddie"})],
            GITHUB_EMAILS_URL: [(200, [{"email": owner, "primary": True, "verified": True}])],
        }
    )


def test_browser_github_login_ignores_stale_session_owner(tmp_path):
    """A plain LOGIN (no ?link=1) MUST use the freshly-proven GitHub identity and IGNORE
    any existing arena_session — else a stale/shared-browser cookie for a DIFFERENT user
    would mint a session for + write an account_link to the WRONG owner (#522 review P1,
    account-takeover on the GA 'Continue with GitHub' CTA)."""
    foreign_owner = "someone-else@example.test"
    gw = _gateway(tmp_path, transport=_github_transport())
    assert gw.session_auth is not None
    stale = gw.session_auth.mint_session(foreign_owner, f"email:{foreign_owner}")
    with _client(gw) as c:
        start = c.get("/auth/github?next=/enroll", follow_redirects=False)
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        return_to = _cookie_value(start, "arena_oauth_return_to")
        # a plain login start never sets link intent (it clears any stale one — see
        # test_browser_github_login_start_clears_stale_link_cookie)
        assert '="1"' not in _setcookie(start, "arena_oauth_link")
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={
                "arena_session": stale,  # foreign/stale session — must NOT win
                "arena_oauth_state": state,
                "arena_oauth_pkce": verifier,
                "arena_oauth_return_to": return_to,
            },
            follow_redirects=False,
        )
    assert done.status_code == 303, done.text
    # GitHub id is linked to the PROVEN owner, not the stale cookie owner
    assert gw.accounts.owner_for(_GH_ID) == _OWNER
    claims = gw.session_auth.verify_session(_cookie_value(done, "arena_session"))
    assert claims.owner == _OWNER and claims.github_id == _GH_ID


def test_browser_github_login_preserves_existing_github_owner_link(tmp_path):
    original_owner = "old-primary@example.test"
    changed_primary = "new-primary@example.test"
    gw = _gateway(tmp_path, transport=_github_transport(owner=changed_primary))
    assert gw.session_auth is not None
    gw.events.append("account_link", {"github_id": _GH_ID, "owner": original_owner})
    gw.accounts.link(_GH_ID, original_owner)

    with _client(gw) as c:
        start = c.get("/auth/github?next=/enroll", follow_redirects=False)
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        return_to = _cookie_value(start, "arena_oauth_return_to")
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={
                "arena_oauth_state": state,
                "arena_oauth_pkce": verifier,
                "arena_oauth_return_to": return_to,
            },
            follow_redirects=False,
        )

    assert done.status_code == 303, done.text
    assert gw.accounts.owner_for(_GH_ID) == original_owner
    claims = gw.session_auth.verify_session(_cookie_value(done, "arena_session"))
    assert claims.owner == original_owner and claims.github_id == _GH_ID
    account_link_events = [e for e in gw.events.iter_events() if e.get("type") == "account_link"]
    assert len(account_link_events) == 1
    assert account_link_events[0]["payload"] == {"github_id": _GH_ID, "owner": original_owner}


def test_browser_github_link_flow_preserves_owner(tmp_path):
    """The EXPLICIT account-link flow (/auth/github?link=1) attaches the proven GitHub id
    to the CURRENT session's owner after a logged-in CSRF proof — the legitimate
    'connect GitHub to my account' case."""
    invite_owner = "invitee@example.test"
    gw = _gateway(tmp_path, transport=_github_transport())
    assert gw.session_auth is not None
    existing = gw.session_auth.mint_session(invite_owner, f"email:{invite_owner}")
    with _client(gw) as c:
        start = c.get(
            "/auth/github?link=1&csrf=csrf-abc&next=/enroll",
            cookies={"arena_session": existing, "arena_csrf": "csrf-abc"},
            follow_redirects=False,
        )
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        return_to = _cookie_value(start, "arena_oauth_return_to")
        link = _cookie_value(start, "arena_oauth_link")
        assert link == state  # explicit link intent is bound to this OAuth round trip
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={
                "arena_session": existing,
                "arena_oauth_state": state,
                "arena_oauth_pkce": verifier,
                "arena_oauth_return_to": return_to,
                "arena_oauth_link": link,
            },
            follow_redirects=False,
        )
    assert done.status_code == 303, done.text
    assert gw.accounts.owner_for(_GH_ID) == invite_owner
    claims = gw.session_auth.verify_session(_cookie_value(done, "arena_session"))
    assert claims.owner == invite_owner and claims.github_id == _GH_ID


def test_browser_github_link_start_rejects_public_query_flag_without_csrf(tmp_path):
    """A crafted top-level /auth/github?link=1 URL must not be enough to preserve an
    ambient arena_session owner; link starts require the readable CSRF proof."""
    foreign_owner = "someone-else@example.test"
    gw = _gateway(tmp_path, transport=_github_transport())
    assert gw.session_auth is not None
    stale = gw.session_auth.mint_session(foreign_owner, f"email:{foreign_owner}")
    with _client(gw) as c:
        missing = c.get(
            "/auth/github?link=1&next=/enroll",
            cookies={"arena_session": stale},
            follow_redirects=False,
        )
        mismatch = c.get(
            "/auth/github?link=1&csrf=attacker&next=/enroll",
            cookies={"arena_session": stale, "arena_csrf": "real"},
            follow_redirects=False,
        )
    assert missing.status_code == 403
    assert mismatch.status_code == 403
    assert _setcookie(missing, "arena_oauth_link") == ""
    assert _setcookie(mismatch, "arena_oauth_link") == ""


def test_browser_github_login_start_clears_stale_link_cookie(tmp_path):
    """A plain /auth/github login start must CLEAR any stale arena_oauth_link left by an
    abandoned earlier ?link=1 — else the leftover cookie (alive for the OAuth TTL) makes
    the callback preserve the existing session's owner and re-opens the #529 takeover."""
    gw = _gateway(tmp_path, transport=_github_transport())
    assert gw.session_auth is not None
    foreign_owner = "someone-else@example.test"
    stale = gw.session_auth.mint_session(foreign_owner, f"email:{foreign_owner}")
    with _client(gw) as c:
        # 1) Simulate an abandoned earlier link round trip (link cookie now stale).
        # 2) a later plain login start must emit a CLEAR for the link cookie
        start = c.get(
            "/auth/github?next=/enroll",
            cookies={"arena_session": stale, "arena_oauth_link": "stale-link-state"},
            follow_redirects=False,
        )
        cleared = _setcookie(start, "arena_oauth_link")
        assert cleared != "" and '="1"' not in cleared  # a delete, not a set
        # 3) the callback (client jar now has the cleared cookie) treats it as LOGIN
        state = _cookie_value(start, "arena_oauth_state")
        verifier = _cookie_value(start, "arena_oauth_pkce")
        return_to = _cookie_value(start, "arena_oauth_return_to")
        done = c.get(
            f"/oauth/github?code=abc123&state={state}",
            cookies={
                "arena_session": stale,
                "arena_oauth_state": state,
                "arena_oauth_pkce": verifier,
                "arena_oauth_return_to": return_to,
            },
            follow_redirects=False,
        )
    assert done.status_code == 303, done.text
    # proven identity wins — the stale link cookie did NOT leak link intent into this login
    assert gw.accounts.owner_for(_GH_ID) == _OWNER
    claims = gw.session_auth.verify_session(_cookie_value(done, "arena_session"))
    assert claims.owner == _OWNER


def test_browser_github_callback_rejects_state_mismatch(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport({}))
    with _client(gw) as c:
        r = c.get(
            "/oauth/github?code=abc123&state=attacker",
            cookies={"arena_oauth_state": "real", "arena_oauth_pkce": "verifier"},
            follow_redirects=False,
        )
    assert r.status_code == 403


def test_successful_login_writes_durable_account_link(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport(_authorized_script()))
    with _client(gw) as c:
        c.post("/auth/device/poll", json={"device_code": "dev-abc"})  # pending
        c.post("/auth/device/poll", json={"device_code": "dev-abc"})  # authorized
    # in-memory link is live
    assert gw.accounts.owner_for(_GH_ID) == _OWNER
    # and durable: a fresh gateway over the SAME log rehydrates it
    gw2 = _gateway(tmp_path)
    assert gw2.accounts.owner_for(_GH_ID) == _OWNER


def test_poll_denied_is_200_status_denied(tmp_path):
    script = {GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "access_denied"})]}
    gw = _gateway(tmp_path, transport=_FakeTransport(script))
    with _client(gw) as c:
        r = c.post("/auth/device/poll", json={"device_code": "dev-abc"})
    assert r.status_code == 200
    assert r.json() == {"status": "denied"}


def test_poll_github_fault_is_502(tmp_path):
    # access_token authorized but /user 401s → DeviceFlowError → opaque 502
    script = {
        GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
        GITHUB_USER_URL: [(401, {"message": "Bad credentials"})],
    }
    gw = _gateway(tmp_path, transport=_FakeTransport(script))
    with _client(gw) as c:
        r = c.post("/auth/device/poll", json={"device_code": "dev-abc"})
    assert r.status_code == 502


def test_poll_rejects_missing_device_code(tmp_path):
    gw = _gateway(tmp_path, transport=_FakeTransport({}))
    with _client(gw) as c:
        r = c.post("/auth/device/poll", json={})
    assert r.status_code == 422  # pydantic body validation


# ---- 503 when unconfigured ----


def test_start_503_when_device_flow_unconfigured(tmp_path):
    gw = _gateway(tmp_path, with_flow=False)
    with _client(gw) as c:
        r = c.post("/auth/device/start")
    assert r.status_code == 503
    assert c.get("/auth/github/status").status_code == 503


def test_poll_503_when_session_auth_unconfigured(tmp_path):
    # device-flow present but no session authority → nothing to mint → 503
    gw = _gateway(tmp_path, transport=_FakeTransport({}), with_session=False)
    with _client(gw) as c:
        r = c.post("/auth/device/poll", json={"device_code": "dev-abc"})
        browser = c.get("/auth/github/status")
    assert r.status_code == 503
    assert browser.status_code == 503


def test_existing_routes_unaffected_when_onboarding_unconfigured(tmp_path):
    """The whole point of optional-at-boot: /ladder etc. still serve when the
    onboarding env is absent."""
    gw = _gateway(tmp_path, with_session=False, with_flow=False)
    with _client(gw) as c:
        assert c.get("/healthz").status_code == 200
        assert c.post("/auth/device/start").status_code == 503
