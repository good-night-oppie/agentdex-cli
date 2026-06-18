"""Minimal HTTP wire client for the agentdex arena — the `adx arena play` TUI driver.

This is a focused port of the canonical standalone client at
``examples/agent-starter-kit/arena_client.py`` (the zero-monorepo-dep on-ramp).
The starter kit stays standalone by design, so the CLI carries its own copy; both
speak the SAME wire (the contract in CLAUDE.md + agentdex_arena.{gateway,consent}).
Keep the two in sync if the wire changes.

Flow: enroll_request -> (owner OOB code) -> enroll_confirm -> token;
battle_start -> sign PoP -> battle_begin -> loop {battle_state, battle_choose} ->
ended receipt -> replay (public). Auth = 7-day Ed25519 consent token; per-battle
proof-of-possession signs ``arena-pop:{token_id}:{nonce}`` with the agent key.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Default to the host that is ACTUALLY live + HTTPS-reachable + canonical in
# skill.md: agentdex.ai-builders.space (the Koyeb arena). `agentdex.builders` is
# the intended AWS home, but its DNS still points at registrar parking (it
# 301s to superlinear.academy) with no TLS, so defaulting there makes `adx arena
# play` time out out-of-box. Re-point this to agentdex.builders once its DNS/TLS
# land (the AWS-PUBLIC-DNS-TLS work, adx-core). Override anytime via --url / env.
DEFAULT_BASE = "https://agentdex.ai-builders.space"


def resolve_base(base: str | None = None) -> str:
    """Resolve the arena base URL: explicit arg > ADX_ARENA_URL/ARENA_BASE env > default."""
    return base or os.environ.get("ADX_ARENA_URL") or os.environ.get("ARENA_BASE") or DEFAULT_BASE


class TokenExpired(RuntimeError):
    """The arena token's own locally-readable expiry is in the past. Recovery:
    re-enroll under a NEW agent_name (names are never freed; the old name keeps
    its ladder history but its token cannot be renewed)."""


@dataclass
class AgentIdentity:
    """An Ed25519 keypair bound to an agent name. The private key signs the
    per-battle proof-of-possession; the public key is registered at enroll."""

    name: str
    priv: Ed25519PrivateKey
    pub_hex: str

    @classmethod
    def new(cls, name: str) -> AgentIdentity:
        priv = Ed25519PrivateKey.generate()
        return cls(name=name, priv=priv, pub_hex=priv.public_key().public_bytes_raw().hex())

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            self.priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        p.chmod(0o600)

    @classmethod
    def load(cls, name: str, path: str | Path) -> AgentIdentity:
        priv = Ed25519PrivateKey.from_private_bytes(Path(path).read_bytes())
        return cls(name=name, priv=priv, pub_hex=priv.public_key().public_bytes_raw().hex())


def decode_claims(token: str) -> dict[str, Any]:
    """Peek at token_id / scopes / expires_at without verifying (debug + expiry check)."""
    payload_b64 = token.split(".", 1)[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def token_expired(token: str, *, now: float | None = None) -> bool:
    """True if the token's own ``expires_at`` is in the past (no network)."""
    try:
        exp = float(decode_claims(token).get("expires_at", 0.0))
    except Exception:
        return False
    return (now if now is not None else time.time()) >= exp


class ArenaClient:
    """Stateless HTTP wrapper; pass ``token`` per call. Use as a context manager."""

    def __init__(self, base: str | None = None, *, timeout: float = 30.0) -> None:
        self.base = resolve_base(base).rstrip("/")
        self._http = httpx.Client(base_url=self.base, timeout=timeout)

    # ---- enroll ----
    def enroll_request(self, *, owner_email: str, agent: AgentIdentity) -> dict[str, Any]:
        if any(c in owner_email for c in "{}<> ") or "@" not in owner_email:
            raise ValueError("owner_email must be a real contact, not a placeholder")
        return (
            self._http.post(
                "/enroll/request",
                json={
                    "owner": owner_email,
                    "agent_name": agent.name,
                    "agent_pubkey_hex": agent.pub_hex,
                },
            )
            .raise_for_status()
            .json()
        )

    def enroll_confirm(self, code: str) -> str:
        """Return the bearer token (7-day; scopes enroll/battle/evolve/badge_mint)."""
        return self._http.post(f"/enroll/confirm/{code}").raise_for_status().json()["token"]

    # ---- battle ----
    def battle_start(self, token: str) -> dict[str, Any]:
        return self._http.post("/battle/start", json={"token": token}).raise_for_status().json()

    def battle_begin(
        self,
        token: str,
        agent: AgentIdentity,
        *,
        team_packed: str | None = None,
        lane: str = "sandbox",
        gym_leader: str | None = None,
    ) -> dict[str, Any]:
        """Two-leg: /battle/start -> sign PoP -> /battle/begin. Returns initial state."""
        # Validate BEFORE the PoP handshake so an invalid request never burns a
        # battle_nonce / a /battle/start round-trip.
        if gym_leader is not None and lane == "rated":
            raise ValueError("gym_leader is sandbox-only")
        start = self.battle_start(token)
        challenge = start["pop_challenge"].encode()
        body: dict[str, Any] = {
            "token": token,
            "battle_nonce": start["battle_nonce"],
            "pop_signature_hex": agent.priv.sign(challenge).hex(),
            "lane": lane,
        }
        if team_packed is not None:
            body["team"] = team_packed
        if gym_leader is not None:
            body["gym_leader"] = gym_leader
        return self._http.post("/battle/begin", json=body).raise_for_status().json()

    def team_draft(self, token: str, export: str) -> dict[str, Any]:
        """Validate + pack a Showdown export against the pinned banlist.
        Returns {packed, valid, errors}."""
        return (
            self._http.post("/team/draft", json={"token": token, "export": export})
            .raise_for_status()
            .json()
        )

    def battle_state(self, token: str, battle_id: str) -> dict[str, Any]:
        """Poll without choosing. Token in the Authorization header (never the query)."""
        return (
            self._http.get(
                f"/battle/{battle_id}/state",
                headers={"Authorization": f"Bearer {token}"},
            )
            .raise_for_status()
            .json()
        )

    def battle_choose(self, token: str, battle_id: str, choice_index: int) -> dict[str, Any]:
        """choice_index is 1-based (1..n_choices). Returns next state OR ended receipt."""
        return (
            self._http.post(
                f"/battle/{battle_id}/choose",
                json={"token": token, "choice_index": choice_index},
            )
            .raise_for_status()
            .json()
        )

    def replay(self, battle_id: str) -> dict[str, Any]:
        """Public — no token. The de-facto spectator surface."""
        return self._http.get(f"/replay/{battle_id}").raise_for_status().json()

    def ladder(self) -> dict[str, Any]:
        return self._http.get("/ladder").raise_for_status().json()

    def whoami(self, token: str) -> dict[str, Any]:
        try:
            return (
                self._http.get("/whoami", headers={"Authorization": f"Bearer {token}"})
                .raise_for_status()
                .json()
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403) and token_expired(token):
                raise TokenExpired(str(TokenExpired.__doc__)) from e
            raise

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ArenaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "AgentIdentity",
    "ArenaClient",
    "TokenExpired",
    "DEFAULT_BASE",
    "decode_claims",
    "resolve_base",
    "token_expired",
]
