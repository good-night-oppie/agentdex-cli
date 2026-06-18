"""Admission control: per-owner concurrency cap + Retry-After (ADMIT-P1).

One owner must not fill the shared sidecar pool and starve everyone else. The cap
keys on the NORMALIZED owner (survives token rotation, like the battle quota) and
is enforced in battle_begin BEFORE any sidecar work, returning 429 + Retry-After.

Tested by calling gateway.battle_begin directly (the cap check is pre-sidecar), so
these run without the node sidecar installed — unlike the full HTTP begin path.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from adx_showdown.sidecar import SidecarError
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, _normalize_owner
from agentdex_arena.gateway import ArenaGateway, BattleSession, BeginRequest, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

_OWNER = "eddie@oppie.xyz"


@pytest.fixture()
def gw(tmp_path: Path):
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    # create_app side-effects nothing we need, but mirrors the real wiring.
    create_app(gateway, sidecar_factory=lambda: None)
    return gateway


class _SentinelSidecar:
    """A sidecar whose start raises a NON-capacity error — proves battle_begin got
    PAST the per-owner cap (the cap would have 429'd before touching the sidecar)."""

    returncode = None

    async def request(self, op: str, **kwargs):
        raise SidecarError("sentinel: sidecar not really running")


def _token(gw: ArenaGateway, agent_key, *, owner: str = _OWNER, name: str = "PartnerBot") -> str:
    claims = ConsentClaims(
        token_id=uuid.uuid4().hex[:16],
        owner=owner,
        agent_name=name,
        agent_pubkey_hex=agent_key.public_key().public_bytes_raw().hex(),
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=gw.now(),
        expires_at=gw.now() + 7 * 86_400,
        confirmed_via="test",
    )
    return gw.authority.mint(claims)


def _begin_req(gw: ArenaGateway, token: str, agent_key) -> BeginRequest:
    start = gw.battle_start(token)
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    return BeginRequest(
        token=token, battle_nonce=start["battle_nonce"], pop_signature_hex=sig, lane="sandbox"
    )


def _dummy(owner: str, i: int) -> BattleSession:
    return BattleSession(
        battle_id=f"sandbox-dummy-{i}",
        claims_token_id="tok",
        visitor_name="PartnerBot",
        lane="sandbox",
        opponent="anchor-random",
        seed=[1, 2, 3, 4],
        sidecar=None,  # type: ignore[arg-type]  — cap check only reads .owner
        opponent_policy=None,
        owner=owner,
    )


async def _call_begin(gw, req):
    return await gw.battle_begin(req, sidecar=_SentinelSidecar())


def test_per_owner_cap_429_with_retry_after(gw):
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    owner_norm = _normalize_owner(_OWNER)
    for i in range(3):  # default ARENA_MAX_BATTLES_PER_OWNER=3
        gw.sessions[f"sandbox-dummy-{i}"] = _dummy(owner_norm, i)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_call_begin(gw, req))
    assert ei.value.status_code == 429
    assert ei.value.headers["Retry-After"] == "5"


def test_cap_keys_on_owner_not_token_id(gw):
    """5 live battles under a DIFFERENT owner do NOT count → this owner gets past
    the cap (and then hits the sentinel sidecar, proving it passed the check)."""
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    for i in range(5):
        gw.sessions[f"other-{i}"] = _dummy(_normalize_owner("someone-else@example.com"), i)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(SidecarError):  # got past the cap → reached the sentinel sidecar
        asyncio.run(_call_begin(gw, req))


def test_env_tightens_cap(gw, monkeypatch):
    monkeypatch.setenv("ARENA_MAX_BATTLES_PER_OWNER", "1")
    agent_key = Ed25519PrivateKey.generate()
    token = _token(gw, agent_key)
    gw.sessions["one"] = _dummy(_normalize_owner(_OWNER), 0)

    req = _begin_req(gw, token, agent_key)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_call_begin(gw, req))
    assert ei.value.status_code == 429
