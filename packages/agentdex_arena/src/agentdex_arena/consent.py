"""Owner-minted consent tokens — Ed25519, capability-scoped, PoP-bound (A1).

The anti-Clawvard consent model (their enrollment is an unauthenticated
self-declared POST): here, an agent acts ONLY under a token its human owner
minted, every capability is scoped and quota'd, enrollment requires an
out-of-band human confirmation an agent cannot complete alone, and per-battle
tokens carry proof-of-possession (a leaked bearer alone is useless).

Key handling: the arena's signing key arrives via env (ARENA_SIGNING_KEY_HEX,
set as a platform env var at deploy — never in the repo). Token format is
deliberately boring: base64url(payload-json) + "." + base64url(signature).
Separate from AgentsRegistry by design (security refutation: registry surface
must not be a forgery accelerant).

Call-order contract for gated endpoints (ADR-0011 §Membership gate call order):

    claims = authority.verify(token, scope=X)        # signature + expiry + scope
    authority.verify_membership(claims)              # paid-feature gate (post 11b)
    authority.spend_quota(claims, scope=X)           # daily cap
    # ... then run the business logic

verify_membership is a no-op for free endpoints (callers don't invoke it);
the membership table is keyed by normalized owner so it survives the 7-day
token rotation (re-enrolling does not lose membership).
"""

from __future__ import annotations

import base64
import os
import time
import unicodedata
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["enroll", "battle", "evolve", "badge_mint"]
SIGNING_KEY_ENV = "ARENA_SIGNING_KEY_HEX"
_OWNER_MAX_LEN = 254  # RFC 5321 email maximum


def _normalize_owner(s: str) -> str:
    """Canonical key for the memberships table (ADR-0011).

    Strategy: NFKC-normalize Unicode (collapses width/compat variants), strip
    surrounding whitespace, lowercase. Bound to RFC 5321 email max (254 chars).
    Reject empty + control characters (those produce silently-disjoint
    memberships for the same owner when stored as dict keys).

    Applied at:
      - EnrollRequest validation (every owner the gateway accepts as input)
      - AdminAuthority grant-membership request validation
      - verify_membership lookup (so case/whitespace mismatch can't bypass)
    """
    if not isinstance(s, str):
        raise ValueError("owner must be a string")
    norm = unicodedata.normalize("NFKC", s).strip().lower()
    if not norm:
        raise ValueError("owner cannot be empty")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in norm):
        raise ValueError("owner contains control characters")
    if len(norm) > _OWNER_MAX_LEN:
        raise ValueError(f"owner exceeds {_OWNER_MAX_LEN} char max")
    return norm


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class ConsentClaims(BaseModel):
    """The owner's grant. `quotas` are per-UTC-day caps (battle:5, evolve:2
    defaults per ADR-0010); `agent_pubkey_hex` binds the token to the
    AGENT's keypair so per-battle PoP works (A1)."""

    model_config = ConfigDict(extra="forbid", strict=False)
    token_id: str = Field(min_length=8)
    owner: str = Field(min_length=1)  # owner contact/handle (human)
    agent_name: str = Field(min_length=1)  # sanitized upstream
    agent_pubkey_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    scopes: list[Scope]
    quotas: dict[str, int] = Field(
        default_factory=lambda: {"battle": 5, "evolve": 2, "badge_mint": 5}
    )
    issued_at: float
    expires_at: float
    confirmed_via: str = Field(min_length=1)  # the out-of-band human action record


class ConsentError(ValueError):
    """Token invalid / expired / revoked / scope or PoP failure."""


class ConsentAuthority:
    """Mints + verifies consent tokens; tracks revocations + daily quotas.

    Revocations and quota counts live in the injected stores (the gateway
    persists them to the durable event log; tests use dicts)."""

    def __init__(
        self,
        *,
        signing_key_hex: str | None = None,
        revoked: set[str] | None = None,
        quota_used: dict[str, int] | None = None,
        memberships: dict[str, float] | None = None,
        now: callable = time.time,
    ) -> None:
        key_hex = signing_key_hex or os.environ.get(SIGNING_KEY_ENV, "")
        if not key_hex:
            raise ConsentError(f"{SIGNING_KEY_ENV} not set — refusing (fail-closed)")
        self._key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
        self.public_key_hex = self._key.public_key().public_bytes_raw().hex()
        self.revoked = revoked if revoked is not None else set()
        self.quota_used = quota_used if quota_used is not None else {}
        # Per-owner membership table (ADR-0011, 11b). Keyed by normalized owner
        # (NFKC + strip + lowercase). Value is the unix epoch the membership
        # expires (lazy expiry: verify_membership checks _now() each call;
        # no cron sweep). Gateway hydrates from EventLog at boot (membership_grant
        # events replay into this dict).
        self.memberships = memberships if memberships is not None else {}
        self._now = now

    # ---- minting (owner-side; the gateway exposes this ONLY behind the
    # out-of-band confirmation flow) ----

    def mint(self, claims: ConsentClaims) -> str:
        payload = claims.model_dump_json().encode()
        sig = self._key.sign(payload)
        return f"{_b64e(payload)}.{_b64e(sig)}"

    # ---- verification (every gateway call) ----

    def verify(self, token: str, *, scope: Scope) -> ConsentClaims:
        try:
            payload_b64, sig_b64 = token.split(".", 1)
            payload = _b64d(payload_b64)
            self._key.public_key().verify(_b64d(sig_b64), payload)
        except (ValueError, InvalidSignature) as e:
            raise ConsentError("bad token signature") from e
        claims = ConsentClaims.model_validate_json(payload)
        if claims.token_id in self.revoked:
            raise ConsentError("token revoked by owner")
        if self._now() > claims.expires_at:
            raise ConsentError("token expired")
        if scope not in claims.scopes:
            raise ConsentError(f"scope {scope!r} not granted")
        return claims

    def quota_key(self, claims: ConsentClaims, *, scope: Scope) -> str:
        """The per-day quota counter key. Scope-conditional per ADR-0011 §3b §5e:

        - `battle` keys on `_normalize_owner(claims.owner)` so /enroll/reissue
          cannot reset the daily rated-battle cap by minting a fresh token_id
          (closes the §3a rotation-as-reset bypass).
        - Every other scope (`evolve`, `badge_mint`, future `export`, …) keys
          on `claims.agent_name` — stable across /enroll/reissue (same
          agent_name, new token_id) AND unique per agent (no cross-agent
          pooling). A multi-agent owner's two agents keep independent
          non-battle budgets, and reissue cannot reset them.

        UTC day-stamped (gmtime) so the cap resets at the UTC boundary.
        spend_quota, check_quota AND the durable `quota_spend` event all derive
        their key here, so the live counter and the replayed-at-boot counter are
        byte-identical (ADX-P2-004 quota persistence).
        """
        return self.quota_key_for(claims.owner, claims.agent_name, scope=scope)

    def quota_key_for(self, owner: str, agent_name: str, *, scope: Scope) -> str:
        """The same day-stamped counter key as ``quota_key`` but from raw
        ``(owner, agent_name)`` rather than a full ``ConsentClaims`` — so the
        read-only account quota surface (ADR-0013 D6) reports against the EXACT
        bytes ``spend_quota`` debits, with no second copy of the key formula to
        drift. ``quota_key`` delegates here, keeping one source of truth."""
        day = time.strftime("%Y%m%d", time.gmtime(self._now()))
        if scope == "battle":
            return f"{_normalize_owner(owner)}:{scope}:{day}"
        return f"{agent_name}:{scope}:{day}"

    def current_utc_day(self) -> str:
        """The UTC day-stamp the quota keys are bucketed under right now (the
        authority's own clock), so a caller's day label can't skew from its
        keys across the UTC-midnight boundary."""
        return time.strftime("%Y%m%d", time.gmtime(self._now()))

    def account_quota_report(self, owner: str, agent_names: list[str]) -> dict:
        """The ADR-0013 D6 ``GET /account/quota`` body for one account.

        ``battle`` is owner-pooled (one counter per account, keyed on normalized
        owner); ``evolve`` / ``badge_mint`` are per-agent, nested under each
        ``agent_name`` from the account->agents join. Caps are the canonical
        ``ConsentClaims.quotas`` defaults (every token mints with these today),
        ``remaining = max(0, cap - used)`` for TODAY's key. Read-only — it never
        debits and is never an input to ladder recompute, so the anti-pay-to-rank
        invariant is unaffected."""
        caps = ConsentClaims.model_fields["quotas"].get_default(call_default_factory=True)

        def block(key: str, cap: int) -> dict:
            return {"remaining": max(0, cap - self.quota_used.get(key, 0)), "cap": cap}

        battle_key = self.quota_key_for(owner, "", scope="battle")
        agents: dict[str, dict] = {}
        for name in agent_names:
            agents[name] = {
                "evolve": block(self.quota_key_for(owner, name, scope="evolve"), caps["evolve"]),
                "badge_mint": block(
                    self.quota_key_for(owner, name, scope="badge_mint"), caps["badge_mint"]
                ),
            }
        return {
            "utc_day": self.current_utc_day(),
            "battle": block(battle_key, caps["battle"]),
            "agents": agents,
        }

    def spend_quota(self, claims: ConsentClaims, *, scope: Scope) -> tuple[int, str]:
        """Atomically count a use against the per-day quota. Fail-closed.

        Returns ``(remaining, key)`` — the remaining budget after this debit and
        the exact day-stamped counter key that was debited. The gateway appends
        the returned key into a durable ``quota_spend`` event so the in-memory
        counter survives a restart (ADX-P2-004); returning the key actually
        debited — rather than letting the caller recompute it — closes the
        UTC-midnight day-skew window where a recomputed key could land in a
        different day bucket than the spend.

        Scope-conditional keying per ADR-0011 §3b §5e: see quota_key.
        """
        key = self.quota_key(claims, scope=scope)
        used = self.quota_used.get(key, 0)
        cap = claims.quotas.get(scope, 0)
        if used >= cap:
            raise ConsentError(f"{scope} quota exhausted ({used}/{cap} today)")
        self.quota_used[key] = used + 1
        return cap - used - 1, key

    def check_quota(self, claims: ConsentClaims, *, scope: Scope) -> None:
        """Read-only quota probe — raises ConsentError if the cap is already hit.

        Does NOT increment the counter; callers must still follow up with
        spend_quota (which is the authoritative debit). Use this as a
        fast-fail guard before expensive work so already-exhausted agents
        receive a 403 without burning sidecar resources.
        """
        key = self.quota_key(claims, scope=scope)
        used = self.quota_used.get(key, 0)
        cap = claims.quotas.get(scope, 0)
        if used >= cap:
            raise ConsentError(f"{scope} quota exhausted ({used}/{cap} today)")

    def replay_quota_spend(self, key: str) -> None:
        """Re-fold a durable ``quota_spend`` event into the in-memory counter at
        boot (ADX-P2-004), mirroring how ``membership_grant`` events rehydrate
        ``memberships``. Only TODAY's keys matter — the cap is per-UTC-day — so a
        prior-day key self-drops. Uses the authority's OWN clock (the same one
        that stamped the key) so a test/prod clock injectable cannot skew the day
        window and mis-drop today's keys. A dropped key only ever under-counts
        (fresh quota), never wrongly locks a user out.
        """
        day = time.strftime("%Y%m%d", time.gmtime(self._now()))
        if isinstance(key, str) and key.endswith(f":{day}"):
            self.quota_used[key] = self.quota_used.get(key, 0) + 1

    def revoke(self, token_id: str) -> None:
        self.revoked.add(token_id)

    # ---- per-owner monthly membership gate (ADR-0011, 11b) ----

    def verify_membership(self, claims: ConsentClaims) -> None:
        """Raise ConsentError('membership required') unless the claims' owner
        has an active membership (valid_until_epoch > now). Lazy expiry —
        no cron, no separate sweep. Keyed by normalized owner so it survives
        7-day token rotation. Free endpoints DO NOT call this; only paid-feature
        routes do."""
        owner_key = _normalize_owner(claims.owner)
        valid_until = self.memberships.get(owner_key)
        if valid_until is None or valid_until <= self._now():
            raise ConsentError("membership required")

    def grant_membership(self, owner: str, valid_until_epoch: float) -> str:
        """Helper used by both the admin endpoint and the EventLog replay path.

        Returns the normalized owner key (so callers can include it in the
        emitted event payload truthfully). Last-write-wins on (owner) — caller
        is responsible for ordering events at replay time (EventLog iter is
        chronological, so replay naturally satisfies this).
        """
        owner_key = _normalize_owner(owner)
        self.memberships[owner_key] = float(valid_until_epoch)
        return owner_key

    # ---- per-battle proof-of-possession (A1: leaked bearer is useless) ----

    @staticmethod
    def pop_challenge(battle_nonce: str, token_id: str) -> bytes:
        return f"arena-pop:{token_id}:{battle_nonce}".encode()

    @staticmethod
    def verify_pop(claims: ConsentClaims, battle_nonce: str, signature_hex: str) -> None:
        agent_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(claims.agent_pubkey_hex))
        try:
            agent_pub.verify(
                bytes.fromhex(signature_hex),
                ConsentAuthority.pop_challenge(battle_nonce, claims.token_id),
            )
        except (ValueError, InvalidSignature) as e:
            raise ConsentError("proof-of-possession failed") from e
