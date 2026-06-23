"""GitHub device-flow broker for ``adx login`` (ADR-0013 D2).

The arena backend — not the CLI — owns the GitHub OAuth app, so the CLI never
sees the client secret (D2). This module brokers the three GitHub calls:

  1. ``POST /login/device/code``    → a user_code the human types at github.com
  2. ``POST /login/oauth/access_token`` (polled) → the access token once granted
  3. ``GET /user`` + ``GET /user/emails`` → the github_id + primary VERIFIED email

and hands the gateway back a proven ``(github_id, owner_email)`` to mint a
session token from (the verified email is the canonical account key — D3).

Deliberately **synchronous + transport-injected**: the route handler calls it
under ``asyncio.to_thread`` (the same off-loop pattern the judge SDK calls use),
and tests inject a fake transport so the GitHub protocol is exercised with zero
network. The default transport is stdlib ``urllib`` so the library adds no new
dependency.

Config via env (operator-held): ``GITHUB_OAUTH_CLIENT_ID`` (required — absent
means device-flow is unconfigured and the routes 503) and
``GITHUB_OAUTH_CLIENT_SECRET`` (optional; included in the token exchange when
set — OAuth-App device flow does not require it, confidential clients may).
"""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

OAUTH_CLIENT_ID_ENV = "GITHUB_OAUTH_CLIENT_ID"
OAUTH_CLIENT_SECRET_ENV = (
    "GITHUB_OAUTH_CLIENT_SECRET"  # pragma: allowlist secret  # env var NAME, not a value
)

DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
# read:user gets the numeric id; user:email is required for /user/emails so we
# can resolve the PRIMARY VERIFIED email (the canonical owner key) even when the
# user's public profile email is private.
DEFAULT_SCOPE = "read:user user:email"
_DEFAULT_INTERVAL = 5

# (method, url, headers, json_body) -> (status_code, parsed_json)
Transport = Callable[[str, str, dict, dict | None], "tuple[int, dict]"]


class DeviceFlowError(Exception):
    """Device-flow misconfiguration, transport failure, or an identity that
    cannot yield a verified email. The route maps this to an opaque 502/503;
    it is distinct from the normal pending/denied/expired poll outcomes."""


@dataclass(frozen=True)
class DeviceStart:
    """The fields ``/auth/device/start`` returns to the CLI (D2 frozen shape).

    ``device_code`` IS returned to the CLI by design — the CLI holds it and
    presents it back on each poll, so the arena stays stateless between
    start and poll (GitHub tracks the grant)."""

    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int

    def to_public(self) -> dict:
        return {
            "user_code": self.user_code,
            "verification_uri": self.verification_uri,
            "device_code": self.device_code,
            "interval": self.interval,
            "expires_in": self.expires_in,
        }


@dataclass(frozen=True)
class DevicePoll:
    """One poll outcome. ``pending`` (keep polling), ``denied`` / ``expired``
    (terminal client faults), or ``authorized`` carrying the proven identity."""

    status: Literal["pending", "authorized", "denied", "expired"]
    github_id: str | None = None
    owner: str | None = None  # primary verified email


def _urllib_transport(method: str, url: str, headers: dict, body: dict | None) -> tuple[int, dict]:
    data = _json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https hosts)
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, _json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, _json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise DeviceFlowError(f"github transport error: {e}") from e


class GitHubDeviceFlow:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        transport: Transport | None = None,
        scope: str = DEFAULT_SCOPE,
    ) -> None:
        cid = client_id if client_id is not None else os.environ.get(OAUTH_CLIENT_ID_ENV, "")
        if not cid or not cid.strip():
            raise DeviceFlowError(
                f"{OAUTH_CLIENT_ID_ENV} not set — device-flow unconfigured (routes 503)"
            )
        self.client_id = cid.strip()
        self.client_secret = (
            client_secret
            if client_secret is not None
            else os.environ.get(OAUTH_CLIENT_SECRET_ENV, "")
        ).strip()
        self._transport = transport or _urllib_transport
        self.scope = scope

    @staticmethod
    def _json_headers() -> dict:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def start(self) -> DeviceStart:
        """Begin the flow — ask GitHub for a device + user code."""
        status, body = self._transport(
            "POST",
            GITHUB_DEVICE_CODE_URL,
            self._json_headers(),
            {"client_id": self.client_id, "scope": self.scope},
        )
        # A bad client_id (or any GitHub-side fault) returns an error object with
        # no device_code — surface it as a config/transport failure, not a start.
        if status != 200 or not isinstance(body, dict) or "device_code" not in body:
            raise DeviceFlowError(f"device/code failed (status={status}, body={body!r})")
        try:
            return DeviceStart(
                user_code=str(body["user_code"]),
                verification_uri=str(body["verification_uri"]),
                device_code=str(body["device_code"]),
                interval=int(body.get("interval", _DEFAULT_INTERVAL)),
                expires_in=int(body.get("expires_in", 900)),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise DeviceFlowError(f"device/code returned an unexpected shape: {body!r}") from e

    def web_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        """Build the browser OAuth redirect URL.

        The gateway owns ``state`` + PKCE verifier custody in HttpOnly cookies;
        this broker only formats GitHub's authorize request using the same
        client id + minimum scopes as device-flow login."""
        if not redirect_uri or not state or not code_challenge:
            raise DeviceFlowError("redirect_uri, state, and code_challenge are required")
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def exchange_web_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> DevicePoll:
        """Exchange a browser OAuth authorization code and resolve identity.

        The access token is used only to read GitHub identity/email and is not
        persisted. The returned shape intentionally matches ``poll()``'s
        authorized branch so the gateway can mint the existing session token
        and write the same account_link event."""
        if not code or not redirect_uri or not code_verifier:
            raise DeviceFlowError("code, redirect_uri, and code_verifier are required")
        payload = {
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        status, body = self._transport(
            "POST", GITHUB_ACCESS_TOKEN_URL, self._json_headers(), payload
        )
        if not isinstance(body, dict):
            raise DeviceFlowError(f"web access_token returned non-object (status={status})")
        access_token = body.get("access_token")
        if not access_token:
            raise DeviceFlowError(
                f"web access_token unexpected response (status={status}, error={body.get('error')!r})"
            )
        github_id, owner = self._identity(str(access_token))
        return DevicePoll(status="authorized", github_id=github_id, owner=owner)

    def poll(self, device_code: str) -> DevicePoll:
        """Exchange the device_code for a token; on success resolve identity.

        Maps GitHub's documented device-flow errors:
          - ``authorization_pending`` / ``slow_down`` → ``pending`` (keep going)
          - ``access_denied``                         → ``denied`` (user refused)
          - ``expired_token``                         → ``expired``
        Anything else (and a transport failure) raises ``DeviceFlowError``.
        """
        if not isinstance(device_code, str) or not device_code.strip():
            raise DeviceFlowError("device_code required")
        payload = {
            "client_id": self.client_id,
            "device_code": device_code,
            "grant_type": DEVICE_GRANT_TYPE,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        status, body = self._transport(
            "POST", GITHUB_ACCESS_TOKEN_URL, self._json_headers(), payload
        )
        if not isinstance(body, dict):
            raise DeviceFlowError(f"access_token returned non-object (status={status})")

        access_token = body.get("access_token")
        if access_token:
            github_id, owner = self._identity(str(access_token))
            return DevicePoll(status="authorized", github_id=github_id, owner=owner)

        error = body.get("error")
        if error in ("authorization_pending", "slow_down"):
            return DevicePoll(status="pending")
        if error == "access_denied":
            return DevicePoll(status="denied")
        if error == "expired_token":
            return DevicePoll(status="expired")
        raise DeviceFlowError(
            f"access_token unexpected response (status={status}, error={error!r})"
        )

    def _identity(self, access_token: str) -> tuple[str, str]:
        """Resolve ``(github_id, primary_verified_email)`` from an access token.

        The primary VERIFIED email is the canonical owner key (D3); an account
        with no verified email cannot be onboarded — raise rather than mint a
        token under an unverifiable owner."""
        auth = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        ustatus, user = self._transport("GET", GITHUB_USER_URL, auth, None)
        if ustatus != 200 or not isinstance(user, dict) or "id" not in user:
            raise DeviceFlowError(f"/user failed (status={ustatus})")
        github_id = str(user["id"])

        estatus, emails = self._transport("GET", GITHUB_EMAILS_URL, auth, None)
        if estatus != 200 or not isinstance(emails, list):
            raise DeviceFlowError(f"/user/emails failed (status={estatus})")
        owner = _pick_primary_verified_email(emails)
        if owner is None:
            raise DeviceFlowError("no primary verified email on the GitHub account")
        return github_id, owner


def _pick_primary_verified_email(emails: list) -> str | None:
    """Prefer the primary+verified email; fall back to any verified one. An
    unverified email is never eligible (it is not a proven owner)."""
    verified = [
        e
        for e in emails
        if isinstance(e, dict) and e.get("verified") and isinstance(e.get("email"), str)
    ]
    for e in verified:
        if e.get("primary"):
            return str(e["email"])
    return str(verified[0]["email"]) if verified else None


__all__ = [
    "GitHubDeviceFlow",
    "DeviceStart",
    "DevicePoll",
    "DeviceFlowError",
    "GITHUB_AUTHORIZE_URL",
    "OAUTH_CLIENT_ID_ENV",
    "OAUTH_CLIENT_SECRET_ENV",
    "DEFAULT_SCOPE",
]
