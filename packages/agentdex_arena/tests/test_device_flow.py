"""Unit tests for the GitHub device-flow broker (ADR-0013 D2).

A scripted fake transport exercises the full GitHub protocol with zero network:
the device/code start, the polled access_token exchange (pending → slow_down →
authorized, plus denied/expired), and the /user + /user/emails identity
resolution (primary-verified-email selection). Route-level wiring + 503-when-
unconfigured land in the gateway-wiring PR."""

from __future__ import annotations

import pytest
from agentdex_arena.device_flow import (
    GITHUB_ACCESS_TOKEN_URL,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_EMAILS_URL,
    GITHUB_USER_URL,
    OAUTH_CLIENT_ID_ENV,
    DeviceFlowError,
    GitHubDeviceFlow,
)


class FakeTransport:
    """Maps URL -> a queue of (status, body) responses; records every call."""

    def __init__(self, scripted: dict[str, list[tuple[int, dict]]]):
        self._scripted = {k: list(v) for k, v in scripted.items()}
        self.calls: list[tuple[str, str, dict, dict | None]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        queue = self._scripted.get(url)
        if not queue:
            raise AssertionError(f"unexpected/exhausted call to {url}")
        return queue.pop(0)


_CID = "Iv1.deadbeefcafe"


def _flow(scripted, **kw) -> tuple[GitHubDeviceFlow, FakeTransport]:
    t = FakeTransport(scripted)
    return GitHubDeviceFlow(client_id=_CID, transport=t, **kw), t


# ---- config ----


def test_missing_client_id_raises(monkeypatch):
    monkeypatch.delenv(OAUTH_CLIENT_ID_ENV, raising=False)
    with pytest.raises(DeviceFlowError, match="not set"):
        GitHubDeviceFlow(transport=lambda *a: (200, {}))


def test_client_id_read_from_env(monkeypatch):
    monkeypatch.setenv(OAUTH_CLIENT_ID_ENV, "Iv1.fromenv")
    flow = GitHubDeviceFlow(transport=lambda *a: (200, {}))
    assert flow.client_id == "Iv1.fromenv"


# ---- start ----


def test_start_returns_frozen_contract_fields():
    flow, t = _flow(
        {
            GITHUB_DEVICE_CODE_URL: [
                (
                    200,
                    {
                        "device_code": "dev-123",
                        "user_code": "ABCD-1234",
                        "verification_uri": "https://github.com/login/device",
                        "interval": 5,
                        "expires_in": 900,
                    },
                )
            ]
        }
    )
    start = flow.start()
    pub = start.to_public()
    assert pub == {
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "device_code": "dev-123",
        "interval": 5,
        "expires_in": 900,
    }
    # the start call carried our client_id + scope
    _, url, _, body = t.calls[0]
    assert url == GITHUB_DEVICE_CODE_URL
    assert body["client_id"] == _CID
    assert "user:email" in body["scope"]


def test_start_defaults_interval_when_absent():
    flow, _ = _flow(
        {
            GITHUB_DEVICE_CODE_URL: [
                (
                    200,
                    {
                        "device_code": "d",
                        "user_code": "U",
                        "verification_uri": "https://x",
                        # no interval / expires_in
                    },
                )
            ]
        }
    )
    start = flow.start()
    assert start.interval == 5
    assert start.expires_in == 900


def test_start_bad_client_id_error_surfaces():
    flow, _ = _flow({GITHUB_DEVICE_CODE_URL: [(200, {"error": "incorrect_client_credentials"})]})
    with pytest.raises(DeviceFlowError, match="device/code failed"):
        flow.start()


# ---- poll: pending / denied / expired ----


def test_poll_authorization_pending_is_pending():
    flow, _ = _flow({GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "authorization_pending"})]})
    assert flow.poll("dev-123").status == "pending"


def test_poll_slow_down_is_pending():
    flow, _ = _flow({GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "slow_down"})]})
    assert flow.poll("dev-123").status == "pending"


def test_poll_access_denied_is_denied():
    flow, _ = _flow({GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "access_denied"})]})
    assert flow.poll("dev-123").status == "denied"


def test_poll_expired_token_is_expired():
    flow, _ = _flow({GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "expired_token"})]})
    assert flow.poll("dev-123").status == "expired"


def test_poll_unknown_error_raises():
    flow, _ = _flow({GITHUB_ACCESS_TOKEN_URL: [(200, {"error": "teapot"})]})
    with pytest.raises(DeviceFlowError, match="unexpected"):
        flow.poll("dev-123")


def test_poll_requires_device_code():
    flow, _ = _flow({})
    with pytest.raises(DeviceFlowError, match="device_code required"):
        flow.poll("  ")


# ---- poll: authorized → identity ----


def _authorized_scripts(emails):
    return {
        GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token", "token_type": "bearer"})],
        GITHUB_USER_URL: [(200, {"id": 12345678, "login": "eddie"})],
        GITHUB_EMAILS_URL: [(200, emails)],
    }


def test_poll_authorized_resolves_primary_verified_email():
    flow, t = _flow(
        _authorized_scripts(
            [
                {"email": "alt@x.com", "primary": False, "verified": True},
                {"email": "eddie@oppie.xyz", "primary": True, "verified": True},
            ]
        )
    )
    res = flow.poll("dev-123")
    assert res.status == "authorized"
    assert res.github_id == "12345678"  # stringified
    assert res.owner == "eddie@oppie.xyz"
    # the token-exchange call carried client_id + device_code + grant_type
    exchange_body = t.calls[0][3]
    assert exchange_body["client_id"] == _CID
    assert exchange_body["device_code"] == "dev-123"
    assert exchange_body["grant_type"].endswith("device_code")


def test_poll_authorized_includes_client_secret_when_set():
    flow, t = _flow(
        _authorized_scripts([{"email": "e@x.com", "primary": True, "verified": True}]),
        client_secret="sekret",
    )
    flow.poll("dev-123")
    assert t.calls[0][3]["client_secret"] == "sekret"


def test_poll_omits_client_secret_when_unset():
    flow, t = _flow(_authorized_scripts([{"email": "e@x.com", "primary": True, "verified": True}]))
    flow.poll("dev-123")
    assert "client_secret" not in t.calls[0][3]


def test_poll_falls_back_to_any_verified_when_no_primary():
    flow, _ = _flow(
        _authorized_scripts(
            [
                {"email": "unverified@x.com", "primary": True, "verified": False},
                {"email": "verified@x.com", "primary": False, "verified": True},
            ]
        )
    )
    assert flow.poll("dev-123").owner == "verified@x.com"


def test_poll_no_verified_email_raises():
    flow, _ = _flow(
        _authorized_scripts([{"email": "unverified@x.com", "primary": True, "verified": False}])
    )
    with pytest.raises(DeviceFlowError, match="no primary verified email"):
        flow.poll("dev-123")


def test_poll_user_endpoint_failure_raises():
    flow, _ = _flow(
        {
            GITHUB_ACCESS_TOKEN_URL: [(200, {"access_token": "gho_token"})],
            GITHUB_USER_URL: [(401, {"message": "Bad credentials"})],
        }
    )
    with pytest.raises(DeviceFlowError, match="/user failed"):
        flow.poll("dev-123")
