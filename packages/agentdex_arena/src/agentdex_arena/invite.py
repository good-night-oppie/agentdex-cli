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

import hashlib
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


def hash_invite_code(code: str) -> str:
    """The durable key for an invite code: its SHA-256 hex digest.

    The plaintext code is a bearer secret — anyone holding an unredeemed code can
    claim a beta seat — so ONLY this hash is ever written to the durable event log
    (mirrors AdminAuthority persisting ``token_hash_hex``, never the admin token;
    and the fleet secrets-discipline rule that a secret value must not land
    anywhere a log/snapshot can persist it). Redemption hashes the presented
    plaintext and looks the slot up by hash."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("invite code required")
    return hashlib.sha256(code.encode()).hexdigest()


class InviteStore:
    """In-memory invite maps, hydrated from the EventLog at boot.

    Not thread-safe by itself; the gateway mutates it from the asyncio event loop
    (single-threaded) under the same discipline as the other stores.
    """

    def __init__(self) -> None:
        # code_hash -> redeemer owner (None = minted but unredeemed). The PLAINTEXT
        # code is never stored — only its hash (see hash_invite_code).
        self._codes: dict[str, str | None] = {}
        self._admitted: set[str] = set()  # normalized owners holding a redeemed invite

    # ---- hash-keyed core (the event log carries only the hash, so replay folds
    #      directly through these; the plaintext convenience wrappers below hash) --

    def grant_hash(self, code_hash: str) -> None:
        """Register a minted code by its hash (idempotent — re-granting an existing
        hash on replay leaves its redemption state untouched)."""
        if not isinstance(code_hash, str) or not code_hash:
            raise ValueError("invite code_hash required")
        self._codes.setdefault(code_hash, None)

    def is_redeemable_hash(self, code_hash: str) -> bool:
        """A code (by hash) that exists and has not been redeemed yet."""
        return self._codes.get(code_hash, "used") is None

    def redeem_hash(self, code_hash: str, owner: str) -> str:
        """Redeem the code identified by ``code_hash`` for ``owner``; see redeem()."""
        owner_key = _normalize_owner(owner)
        if owner_key in self._admitted:
            return owner_key  # already in — re-redeem is a no-op, no code burned
        if self._codes.get(code_hash, "used") is not None:
            raise InviteError("invite code is invalid or already used")
        self._codes[code_hash] = owner_key
        self._admitted.add(owner_key)
        return owner_key

    # ---- plaintext convenience (live mint/redeem + unit tests) ----

    def mint(self, code: str) -> None:
        """Register an unused invite code (hashes then delegates to grant_hash)."""
        self.grant_hash(hash_invite_code(code))

    def exists(self, code: str) -> bool:
        try:
            return hash_invite_code(code) in self._codes
        except ValueError:
            return False  # a blank/malformed code simply does not exist

    def redeemable(self, code: str) -> bool:
        """A code that exists and has not been redeemed yet. A blank/malformed code
        is NOT redeemable (returns False) — never raises — so the redemption path
        surfaces a clean InviteError → opaque 403, not an uncaught 500 from hashing
        an empty string (a whitespace-only invite_code passes the request model's
        min_length=1 but has no valid hash). PR #363 review."""
        try:
            return self.is_redeemable_hash(hash_invite_code(code))
        except ValueError:
            return False

    def redeem(self, code: str, owner: str) -> str:
        """Redeem ``code`` for ``owner``; returns the normalized owner key.

        - If the owner is ALREADY admitted, this is a no-op success regardless of
          ``code`` (survives token rotation / re-enrollment — does not burn a code).
        - Else the code must exist and be unredeemed: it is bound to this owner and
          the owner is admitted.
        - Else (unknown or already-used code, owner not yet admitted) → ``InviteError``.

        Raises ``ValueError`` on a malformed owner / code; the caller appends the
        durable event only after this returns, so a bad value reserves nothing.
        """
        return self.redeem_hash(hash_invite_code(code), owner)

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

    def listing(self) -> list[dict[str, str | None]]:
        """Per-code redemption status for the operator audit/reconcile surface:
        ``[{"code_hash": <hash>, "redeemed_by": <owner>|None}, ...]``, sorted by
        hash for a stable diff. Exposes only the HASH (never the plaintext code,
        which is gone after mint) plus the redeemer owner — enough to reconcile a
        distributed batch (an operator who kept the plaintext can hash + match)
        and to see outstanding/unused seats, without re-leaking the secret."""
        return [
            {"code_hash": code_hash, "redeemed_by": owner}
            for code_hash, owner in sorted(self._codes.items())
        ]


__all__ = ["InviteStore", "InviteError", "new_invite_code", "hash_invite_code"]
