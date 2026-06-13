"""Admin bearer-token authority for the arena's operator-only endpoints.

V1 membership grant flow (ADR-0011): an admin sends `X-Admin-Token: <plaintext>`
to `POST /admin/grant-membership`. The gateway hashes the plaintext (SHA-256)
and constant-time-compares it to the env-stored hash. The plaintext NEVER lives
on the server — only its hash, set once at deploy time via Koyeb env.

Fail-closed boot: if `ARENA_ADMIN_TOKEN_HASH` is unset or malformed, the gateway
refuses to start. No degraded-runtime mode; no runtime 503 path that would let an
admin endpoint silently 200 with no protection.

Per-request: `verify_bearer(header_value)` returns the first 8 hex chars of the
hash as an opaque `actor_hash` for audit-log purposes (never the plaintext, never
the full hash). All comparisons use `hmac.compare_digest` — no early-out, no
timing channel.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

ADMIN_TOKEN_HASH_ENV = "ARENA_ADMIN_TOKEN_HASH"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class AdminAuthError(Exception):
    """Raised when admin bearer auth fails. Same _opaque_error(403, ...) handling
    as ConsentError on the gateway side."""


class AdminAuthority:
    """Constant-time SHA-256 bearer check against an env-stored hash.

    Args:
        token_hash_hex: explicit hash override (for tests). When None, reads from
            ARENA_ADMIN_TOKEN_HASH env. Either way, validates that the value is
            64 lowercase hex chars; raises AdminAuthError on missing/malformed.
    """

    def __init__(self, token_hash_hex: str | None = None) -> None:
        raw = token_hash_hex if token_hash_hex is not None else os.environ.get(ADMIN_TOKEN_HASH_ENV)
        if not raw:
            raise AdminAuthError(
                f"{ADMIN_TOKEN_HASH_ENV} not set — admin endpoint will fail-closed at boot"
            )
        if not _HASH_RE.match(raw):
            raise AdminAuthError(f"{ADMIN_TOKEN_HASH_ENV} must be a 64-char lowercase sha256 hex")
        self._hash_hex = raw

    def verify_bearer(self, header_value: str | None) -> str:
        """Verify a presented plaintext token against the stored hash.

        Returns the first 8 hex chars of the hash for audit `actor_hash` (opaque,
        no plaintext leak). Raises AdminAuthError uniformly on every failure mode
        — caller maps to a single _opaque_error(403, ...).
        """
        if not header_value:
            raise AdminAuthError("X-Admin-Token header required")
        # Hash the presented plaintext (NOT the stored hash — never reverse).
        presented_hash = hashlib.sha256(header_value.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(presented_hash, self._hash_hex):
            raise AdminAuthError("admin token mismatch")
        return self._hash_hex[:8]


__all__ = ["AdminAuthError", "AdminAuthority", "ADMIN_TOKEN_HASH_ENV"]
