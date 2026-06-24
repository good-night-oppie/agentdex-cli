"""Human-account session tokens — the agentdex login session (ADR-0013 D2/D3).

A *session* token authenticates a HUMAN to their agentdex account; a *consent*
token (see ``consent.py``) authorizes one AGENT to act. ``adx login`` obtains a
session token via GitHub device-flow (D2); ``adx enroll`` / ``adx status``
present it (D3/D6). The session's ``owner`` is the account's **verified email**
— the SAME key consent tokens use for membership + battle quota (ADR-0011) — so
one human's account, memberships, and per-day quota stay single-keyed across
both token kinds. This is the D3 load-bearing seam: mint the consent token under
``/enroll/account`` with the session's verified email as ``ConsentClaims.owner``
and nothing in the quota/membership model has to change.

Key custody mirrors ``BadgeAuthority`` (D2 blast-radius isolation): a DEDICATED
Ed25519 keypair via ``ARENA_SESSION_SIGNING_KEY_HEX``, read once at boot. A leak
of the session key lets an attacker forge logins, but consent + badge tokens
stay trustworthy; the inverse holds too. Cross-key reuse would conflate trust
domains. Unlike consent (fail-closed-aborts-boot) and like badge, session auth
is **optional at boot**: a deploy without the env keeps the arena serving every
existing surface; only the device-flow + account routes degrade to a 503
("session auth not configured"). That lets the account onboarding land deploy
slot by deploy slot without gating the whole gateway on a new secret.

Token shape: ``base64url(payload-json) + "." + base64url(signature)`` — byte-for-
byte the consent token shape, so the same ``Authorization: Bearer`` extraction
applies to both kinds.
"""

from __future__ import annotations

import os
import re
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, Field

from agentdex_arena.consent import _b64d, _b64e, _normalize_owner

SESSION_SIGNING_KEY_ENV = "ARENA_SESSION_SIGNING_KEY_HEX"
# Strict key format, mirroring BadgeAuthority (the newest sibling authority):
# 64 lowercase hex chars exactly. `bytes.fromhex` alone would accept uppercase
# and any even-length-32-byte seed, silently admitting a mistyped key.
_KEY_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
# Humans re-authenticate far less often than agents rotate their 7-day consent
# tokens, so the login session is longer-lived. 30 days keeps `adx status` from
# nagging a returning player to re-login every week while still bounding a leaked
# ~/.agentdex/session.json. `adx logout` is the client-side immediate revoke
# (deletes the file); server-side revocation is out of the frozen D2 contract.
SESSION_TTL_SEC = 30 * 86_400


class SessionError(ValueError):
    """Session token invalid / expired / malformed, or session auth unconfigured."""


class SessionClaims(BaseModel):
    """A proven human login. ``owner`` is the account's verified email (the
    canonical membership/quota key); ``github_id`` is the federated identity that
    *proved* that email — carried for the account store's ``github_id ↔ owner``
    link (D3) and audit, never itself used as a quota/membership key."""

    model_config = ConfigDict(extra="forbid", strict=False)
    session_id: str = Field(min_length=8)
    owner: str = Field(min_length=1)  # verified email — the canonical account key
    github_id: str = Field(min_length=1)  # federated identity that proved the email
    issued_at: float
    expires_at: float


class SessionAuthority:
    """Mints + verifies human-account session tokens.

    Args:
        signing_key_hex: 64-char lowercase hex (Ed25519 32-byte seed). When
            None, reads ``ARENA_SESSION_SIGNING_KEY_HEX``. Raises
            ``SessionError`` (fail-closed) on missing/malformed — the production
            ``build_gateway`` catches this and leaves session auth unconfigured
            (routes 503) rather than aborting boot.
        now: clock injectable (tests pin it; prod uses ``time.time``).
    """

    def __init__(
        self,
        *,
        signing_key_hex: str | None = None,
        now: callable = time.time,
    ) -> None:
        key_hex = (
            os.environ.get(SESSION_SIGNING_KEY_ENV, "")
            if signing_key_hex is None
            else signing_key_hex
        )
        if not key_hex:
            raise SessionError(f"{SESSION_SIGNING_KEY_ENV} not set — refusing (fail-closed)")
        if not _KEY_HEX_RE.match(key_hex):
            raise SessionError(
                f"{SESSION_SIGNING_KEY_ENV} must be a 64-char lowercase ed25519 hex seed"
            )
        self._key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
        self.public_key_hex = self._key.public_key().public_bytes_raw().hex()
        self._now = now

    def mint_session(self, owner: str, github_id: str, *, ttl_sec: float = SESSION_TTL_SEC) -> str:
        """Issue a session token for a freshly proven login.

        ``owner`` is run through ``_normalize_owner`` to fail-closed on an empty /
        control-char / over-long value BEFORE signing (the same guard the enroll
        path applies), but the ORIGINAL string is stored in the claim so the
        account store + any audit records what the federation actually returned —
        normalization is re-applied at quota/membership key time. A malformed
        email therefore cannot mint a token that later 500s when keyed.
        """
        _normalize_owner(owner)  # validate-but-store-original (raises ValueError on bad input)
        if not isinstance(github_id, str) or not github_id.strip():
            raise SessionError("github_id required")
        issued = self._now()
        claims = SessionClaims(
            session_id=uuid.uuid4().hex[:16],
            owner=owner,
            github_id=github_id,
            issued_at=issued,
            expires_at=issued + ttl_sec,
        )
        payload = claims.model_dump_json().encode()
        sig = self._key.sign(payload)
        return f"{_b64e(payload)}.{_b64e(sig)}"

    def verify_session(self, token: str) -> SessionClaims:
        """Verify signature + expiry; return the claims. Raises ``SessionError``
        on a bad signature, malformed token, or expiry — the route handler maps
        every failure mode to one opaque 401/403 (no enumeration of which)."""
        try:
            payload_b64, sig_b64 = token.split(".", 1)
            payload = _b64d(payload_b64)
            self._key.public_key().verify(_b64d(sig_b64), payload)
        except (ValueError, InvalidSignature) as e:
            raise SessionError("bad session token signature") from e
        claims = SessionClaims.model_validate_json(payload)
        if self._now() > claims.expires_at:
            raise SessionError("session token expired")
        return claims


__all__ = [
    "SessionAuthority",
    "SessionClaims",
    "SessionError",
    "SESSION_SIGNING_KEY_ENV",
    "SESSION_TTL_SEC",
]
