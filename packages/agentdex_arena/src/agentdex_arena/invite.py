"""Invitation-code store — the registration gate for the agentdex.builders beta
(GA-CORE-1). Gates self-serve signup to the first N invited owners.

Two maps, both rebuilt at boot from the durable EventLog (the same
write-ahead-then-replay discipline as ``membership_grant`` / ``account_enroll``):

  - ``code -> redeemer owner | None`` — a minted code (``invite_grant``) and, once
    used, the normalized owner who redeemed it (``invite_redeem``). One-time.
  - ``owner -> admitted`` — the set of normalized owners who hold a redeemed invite;
    this is the beta gate ``is_admitted`` the enroll path checks.

**Owner-keyed admission (load-bearing, mirrors membership):** redemption admits the
*normalized owner* (NFKC + strip + lower), NOT a token. So a returning human who
re-enrolls (new token after the 7-day rotation, or a second agent) is already
admitted and does NOT burn a second code — re-``redeem`` for an admitted owner is a
no-op success. This keeps "100 invited users" == 100 humans, not 100 tokens.

Storage-only — no signing, no HTTP. The gateway appends the durable event BEFORE
admitting the owner / returning a receipt, so a crash can never admit an owner the
log does not record.
"""

from __future__ import annotations

import secrets

from agentdex_arena.consent import _normalize_owner

# Code shape: a URL-safe, unambiguous, operator-pasteable token. 16 hex chars
# (64 bits) is far beyond brute-force for a ≤100-code beta while staying short.
_CODE_NBYTES = 8


class InviteError(Exception):
    """Raised when an invite redemption fails (unknown / already-used code for an
    owner who is not already admitted). Same ``_opaque_error(403, ...)`` handling
    as ConsentError on the gateway side — never reveals which of unknown/used."""


def new_invite_code() -> str:
    """A fresh single-use invite code (16 lowercase hex chars)."""
    return secrets.token_hex(_CODE_NBYTES)


class InviteStore:
    """In-memory invite maps, hydrated from the EventLog at boot.

    Not thread-safe by itself; the gateway mutates it from the asyncio event loop
    (single-threaded) under the same discipline as the other stores.
    """

    def __init__(self) -> None:
        self._codes: dict[str, str | None] = {}  # code -> redeemer owner (None = unused)
        self._admitted: set[str] = set()  # normalized owners holding a redeemed invite

    # ---- mint ----

    def mint(self, code: str) -> None:
        """Register an unused invite code (idempotent on replay — re-minting an
        existing code leaves its redemption state untouched)."""
        if not isinstance(code, str) or not code.strip():
            raise ValueError("invite code required")
        self._codes.setdefault(code, None)

    def exists(self, code: str) -> bool:
        return code in self._codes

    def redeemable(self, code: str) -> bool:
        """A code that exists and has not been redeemed yet."""
        return self._codes.get(code, "used") is None

    # ---- redeem ----

    def redeem(self, code: str, owner: str) -> str:
        """Redeem ``code`` for ``owner``; returns the normalized owner key.

        - If the owner is ALREADY admitted, this is a no-op success regardless of
          ``code`` (survives token rotation / re-enrollment — does not burn a code).
        - Else the code must exist and be unredeemed: it is bound to this owner and
          the owner is admitted.
        - Else (unknown or already-used code, owner not yet admitted) → ``InviteError``.

        Raises ``ValueError`` (from ``_normalize_owner``) on a malformed owner; the
        caller appends the durable event only after this returns, so a bad value
        reserves nothing.
        """
        owner_key = _normalize_owner(owner)
        if owner_key in self._admitted:
            return owner_key  # already in — re-redeem is a no-op, no code burned
        if self._codes.get(code, "used") is not None:
            raise InviteError("invite code is invalid or already used")
        self._codes[code] = owner_key
        self._admitted.add(owner_key)
        return owner_key

    def is_admitted(self, owner: str) -> bool:
        """Whether this owner holds a redeemed invite (the beta gate)."""
        try:
            return _normalize_owner(owner) in self._admitted
        except ValueError:
            return False

    # ---- operator read ----

    def stats(self) -> dict[str, int]:
        """Minted / redeemed / remaining counts for the admin mint receipt."""
        redeemed = sum(1 for v in self._codes.values() if v is not None)
        minted = len(self._codes)
        return {"minted": minted, "redeemed": redeemed, "remaining": minted - redeemed}


__all__ = ["InviteStore", "InviteError", "new_invite_code"]
