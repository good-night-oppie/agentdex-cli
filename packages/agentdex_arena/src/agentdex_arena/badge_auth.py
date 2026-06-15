"""Verified-badge signing authority for the arena's first paid feature (11c).

Ships per the parked design at
`docs/references/2026-06-14-arena-verified-badge-svg-design.md` (ratified
2026-06-15): O1 separate env / O2 30-day TTL / O3 bundled-w/-11c.3.

Key custody: a dedicated Ed25519 keypair separate from `ConsentAuthority`'s
signing key. The env var `ARENA_BADGE_SIGNING_KEY_HEX` is read once at boot;
a leak of the badge key lets an attacker mint fake badges but consent tokens
remain trustworthy. Cross-key reuse would conflate two trust domains.

Fail-closed boot: missing or malformed env aborts construction immediately,
mirroring `AdminAuthority` (PR #101 11b.1). No degraded-runtime mode.

Token shape: `<payload_hex>.<signature_hex>`. Payload is the canonical-JSON
form of the badge claim dict (sort_keys=True, no whitespace) — hex-encoding
keeps the URL path
`@app.get("/badge/{agent_name}/{badge_token}.svg")` URL-safe by construction
without depending on base64url padding rules. The `kid` field (key-id) is
carried in every payload so future rotation (V2) can dispatch on it without
breaking existing tokens.
"""

from __future__ import annotations

import json
import os
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

BADGE_SIGNING_KEY_ENV = "ARENA_BADGE_SIGNING_KEY_HEX"
BADGE_KID_V1 = "badge-v1"
_KEY_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^(?P<payload>[0-9a-f]+)\.(?P<sig>[0-9a-f]{128})$")


class BadgeAuthError(Exception):
    """Raised on any badge-auth failure — boot, sign, or verify. Caller maps to
    a single opaque error response (404 on the public render endpoint per
    spec, to avoid confirming whether the badge_token shape was even close)."""


class BadgeAuthority:
    """Mints + verifies badge tokens.

    Args:
        signing_key_hex: 64-char lowercase hex (Ed25519 32-byte seed). When
            None, reads from ARENA_BADGE_SIGNING_KEY_HEX. Either way validates
            the format; raises BadgeAuthError on missing/malformed.
    """

    def __init__(self, signing_key_hex: str | None = None) -> None:
        raw = (
            signing_key_hex
            if signing_key_hex is not None
            else os.environ.get(BADGE_SIGNING_KEY_ENV)
        )
        if not raw:
            raise BadgeAuthError(
                f"{BADGE_SIGNING_KEY_ENV} not set — badge endpoint will fail-closed at boot"
            )
        if not _KEY_HEX_RE.match(raw):
            raise BadgeAuthError(
                f"{BADGE_SIGNING_KEY_ENV} must be a 64-char lowercase ed25519 hex seed"
            )
        self._key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
        self.public_key_hex = self._key.public_key().public_bytes_raw().hex()

    def sign_badge(self, payload: dict) -> str:
        """Serialize payload as canonical JSON, sign with Ed25519, return
        `<payload_hex>.<signature_hex>`. Caller supplies `{agent_name, signed_at,
        valid_until, kid}` per the spec; this method does NOT validate payload
        shape — `verify_badge` re-parses on the read path."""
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = self._key.sign(payload_bytes)
        return f"{payload_bytes.hex()}.{sig.hex()}"

    def verify_badge(self, badge_token_hex: str) -> dict:
        """Parse + verify a badge token; return its payload dict.

        Raises BadgeAuthError on malformed token, bad signature, or payload that
        is not valid JSON / not a dict. TTL + agent_name match are caller's
        responsibility (per spec: render endpoint compares `payload["agent_name"]
        == path_agent_name` and `now() < payload["valid_until"]`)."""
        if not badge_token_hex:
            raise BadgeAuthError("badge token required")
        m = _TOKEN_RE.match(badge_token_hex)
        if not m:
            raise BadgeAuthError("badge token malformed")
        payload_hex, sig_hex = m.group("payload"), m.group("sig")
        try:
            payload_bytes = bytes.fromhex(payload_hex)
            sig_bytes = bytes.fromhex(sig_hex)
            self._key.public_key().verify(sig_bytes, payload_bytes)
        except (ValueError, InvalidSignature) as e:
            raise BadgeAuthError("bad badge signature") from e
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise BadgeAuthError("badge payload not valid JSON") from e
        if not isinstance(payload, dict):
            raise BadgeAuthError("badge payload must be a JSON object")
        return payload


__all__ = ["BadgeAuthError", "BadgeAuthority", "BADGE_SIGNING_KEY_ENV", "BADGE_KID_V1"]
