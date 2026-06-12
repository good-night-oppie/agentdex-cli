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
"""

from __future__ import annotations

import base64
import os
import time
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["enroll", "battle", "evolve"]
SIGNING_KEY_ENV = "ARENA_SIGNING_KEY_HEX"


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
    quotas: dict[str, int] = Field(default_factory=lambda: {"battle": 5, "evolve": 2})
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
        now: callable = time.time,
    ) -> None:
        key_hex = signing_key_hex or os.environ.get(SIGNING_KEY_ENV, "")
        if not key_hex:
            raise ConsentError(f"{SIGNING_KEY_ENV} not set — refusing (fail-closed)")
        self._key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
        self.public_key_hex = self._key.public_key().public_bytes_raw().hex()
        self.revoked = revoked if revoked is not None else set()
        self.quota_used = quota_used if quota_used is not None else {}
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

    def spend_quota(self, claims: ConsentClaims, *, scope: Scope) -> int:
        """Atomically count a use against the per-day quota. Fail-closed."""
        day = time.strftime("%Y%m%d", time.gmtime(self._now()))
        key = f"{claims.token_id}:{scope}:{day}"
        used = self.quota_used.get(key, 0)
        cap = claims.quotas.get(scope, 0)
        if used >= cap:
            raise ConsentError(f"{scope} quota exhausted ({used}/{cap} today)")
        self.quota_used[key] = used + 1
        return cap - used - 1

    def revoke(self, token_id: str) -> None:
        self.revoked.add(token_id)

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
