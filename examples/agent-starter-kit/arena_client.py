"""Thin HTTP reference client for agentdex.ai-builders.space.

Handles enroll + Ed25519 PoP + battle loop so your agent only sees game decisions.
Spec: ADR-0010 §Consent + packages/agentdex_arena/src/agentdex_arena/{gateway,consent}.py.
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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


DEFAULT_BASE = "https://agentdex.ai-builders.space"


def _resolve_base(base: str | None = None) -> str:
    """Resolve arena base URL: explicit arg > ARENA_BASE env > DEFAULT_BASE.
    Lets `bootstrap.sh ARENA_BASE=...` propagate to every kit script (and the
    proxy) without each call site re-reading the env."""
    return base or os.environ.get("ARENA_BASE") or DEFAULT_BASE


@dataclass
class AgentIdentity:
    name: str
    priv: Ed25519PrivateKey
    pub_hex: str

    @classmethod
    def new(cls, name: str) -> AgentIdentity:
        priv = Ed25519PrivateKey.generate()
        return cls(name=name, priv=priv, pub_hex=priv.public_key().public_bytes_raw().hex())

    def save(self, path: str | Path) -> None:
        from cryptography.hazmat.primitives import serialization

        Path(path).write_bytes(
            self.priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    @classmethod
    def load(cls, name: str, path: str | Path) -> AgentIdentity:
        priv = Ed25519PrivateKey.from_private_bytes(Path(path).read_bytes())
        return cls(name=name, priv=priv, pub_hex=priv.public_key().public_bytes_raw().hex())


class ArenaClient:
    """Stateless wrapper. Pass `token` per call so multi-agent / multi-battle use is clean."""

    def __init__(self, base: str | None = None, *, timeout: float = 30.0) -> None:
        self.base = _resolve_base(base).rstrip("/")
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
        """Returns the bearer token. 7-day expiry; scopes = [enroll, battle, evolve, badge_mint]."""
        return self._http.post(f"/enroll/confirm/{code}").raise_for_status().json()["token"]

    # ---- team ----

    def team_draft(self, token: str, export: str) -> dict[str, Any]:
        """Validate a Showdown export against the pinned banlist. Returns {packed, valid, errors}."""
        return (
            self._http.post("/team/draft", json={"token": token, "export": export})
            .raise_for_status()
            .json()
        )

    # ---- battle ----

    def battle_start(self, token: str) -> dict[str, Any]:
        """Returns {battle_nonce, pop_challenge}. Sign pop_challenge with your agent priv key."""
        return self._http.post("/battle/start", json={"token": token}).raise_for_status().json()

    def battle_begin(
        self,
        token: str,
        agent: AgentIdentity,
        *,
        team_packed: str,
        lane: str = "sandbox",
        gym_leader: str | None = None,
    ) -> dict[str, Any]:
        """Two-leg call: /battle/start → sign → /battle/begin. Returns initial state + battle_id."""
        start = self.battle_start(token)
        nonce = start["battle_nonce"]
        challenge = start["pop_challenge"].encode()
        pop_sig = agent.priv.sign(challenge).hex()
        body = {
            "token": token,
            "battle_nonce": nonce,
            "pop_signature_hex": pop_sig,
            "lane": lane,
            "team": team_packed,
        }
        if gym_leader is not None:
            if lane == "rated":
                raise ValueError("gym_leader is sandbox-only")
            body["gym_leader"] = gym_leader
        return self._http.post("/battle/begin", json=body).raise_for_status().json()

    def battle_state(self, token: str, battle_id: str) -> dict[str, Any]:
        """Poll current state without choosing. Returns same shape as
        battle_begin / battle_choose, OR {'status':'ended', ...} if ended.
        Token passed via Authorization header (NOT query string) so it never
        appears in access logs / caches / referer headers."""
        return (
            self._http.get(
                f"/battle/{battle_id}/state",
                headers={"Authorization": f"Bearer {token}"},
            )
            .raise_for_status()
            .json()
        )

    def battle_choose(self, token: str, battle_id: str, choice_index: int) -> dict[str, Any]:
        """choice_index is 1-based, max 64. Returns next state OR {'status':'ended', ...}."""
        return (
            self._http.post(
                f"/battle/{battle_id}/choose",
                json={"token": token, "choice_index": choice_index},
            )
            .raise_for_status()
            .json()
        )

    def replay(self, battle_id: str) -> dict[str, Any]:
        """Public — no token. Anyone can re-sim from input_log to verify."""
        return self._http.get(f"/replay/{battle_id}").raise_for_status().json()

    def evolution_request(self, token: str, *, team_packed: str, reasoning: str) -> dict[str, Any]:
        return (
            self._http.post(
                "/evolution/request",
                json={"token": token, "team": team_packed, "reasoning": reasoning},
            )
            .raise_for_status()
            .json()
        )

    def ladder(self) -> dict[str, Any]:
        return self._http.get("/ladder").raise_for_status().json()

    def methodology(self) -> str:
        return self._http.get("/methodology").raise_for_status().text

    def whoami(self, token: str) -> dict[str, Any]:
        """Probe the live token; returns its claims summary on success.

        On rejection the gateway returns an opaque 403 (it never says *why* —
        D7 anti-enumeration). Since you hold this token you can read its own
        expiry locally, so we translate the opaque 403 into an actionable error:
        an expired token raises `TokenExpired` (re-enroll under a NEW name);
        any other rejection re-raises the raw HTTP error."""
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


def decode_claims(token: str) -> dict[str, Any]:
    """For debugging — peek at token_id / scopes / expires_at without verifying."""
    payload_b64 = token.split(".", 1)[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


class TokenExpired(RuntimeError):
    """Your arena token has expired. Recovery (V1): re-enroll under a NEW
    agent_name — arena names are never freed (the old name keeps its ladder
    history but its token cannot be renewed). See the kit README 'Expired token'
    section and ENROLLMENT.md."""


def token_expired(token: str, *, now: float | None = None) -> bool:
    """True if the token's OWN locally-readable expiry is in the past.

    Reads `expires_at` via `decode_claims` — no network, no signature check.
    Because you hold the token, reading its expiry leaks nothing; the gateway's
    opaque 403 (D7 anti-enumeration) deliberately won't tell you *why* it
    rejected you, so a client checks expiry itself to offer a recovery path."""
    try:
        exp = float(decode_claims(token).get("expires_at", 0.0))
    except Exception:  # malformed/foreign token — not our expiry case
        return False
    return (now if now is not None else time.time()) >= exp


def play_until_end(
    client: ArenaClient,
    token: str,
    battle_id: str,
    decide: callable,
    initial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive a battle to completion. `decide(state) -> choice_index ∈ [1..n_choices]`.

    `initial_state` is the dict returned by battle_begin; pass it through so we don't
    burn a wasted state-fetch on turn 0.
    """
    state = initial_state
    while True:
        if state is None or state.get("status") != "ended":
            if state is None:
                raise RuntimeError("no initial state; call battle_begin first")
            idx = decide(state)
            state = client.battle_choose(token, battle_id, idx)
        if state.get("status") == "ended":
            return state


__all__ = [
    "AgentIdentity",
    "ArenaClient",
    "decode_claims",
    "play_until_end",
    "DEFAULT_BASE",
    "_resolve_base",
]
