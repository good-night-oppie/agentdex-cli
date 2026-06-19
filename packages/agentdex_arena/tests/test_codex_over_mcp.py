"""SPEC DONE #1 — codex drives self-play moves THROUGH the arena MCP surface.

Drives the real ``selfplay_battle`` MCP tool (A4, #319) with a ``llm_freeform``
(codex) candidate harness vs a held-out baseline rendered as a harness
(``random`` == RandomPlayer). The candidate's every move is resolved by the C1
``select_codex_move`` adapter, so this is codex picking moves over the MCP tool.

CI-safe coverage: the auth boundary + genome validation (no PS server). The live
battle through the tool is PS-gated (needs ADX_PS_HOST/PORT + poke-env)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import ArenaGateway
from agentdex_arena.mcp_surface import init_mcp, selfplay_battle
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_CODEX = {"harness_id": "codex-c1", "move_selection_strategy": "llm_freeform"}
_BASELINE = {"harness_id": "rng", "move_selection_strategy": "random"}


def _gateway(tmp_path: Path) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


def _battle_token(gw: ArenaGateway) -> str:
    return gw.authority.mint(
        ConsentClaims(
            token_id="codextok1",
            owner="eddie@oppie.xyz",
            agent_name="codex",
            agent_pubkey_hex="0" * 64,
            scopes=["battle"],
            issued_at=0.0,
            expires_at=9_999_999_999.0,
            confirmed_via="test",
        )
    )


# ---- CI-safe: auth + genome validation (no PS server) ----


@pytest.mark.asyncio
async def test_bad_token_is_opaque_error(tmp_path):
    init_mcp(_gateway(tmp_path), lambda: None)
    with pytest.raises(ValueError, match="arena error"):
        await selfplay_battle("not.a.token", _CODEX, _BASELINE, seed=1, n_battles=2)


@pytest.mark.asyncio
async def test_malformed_codex_genome_rejected(tmp_path):
    gw = _gateway(tmp_path)
    init_mcp(gw, lambda: None)
    token = _battle_token(gw)
    with pytest.raises(ValueError, match="invalid self-play harness genome"):
        await selfplay_battle(token, {"harness_id": ""}, _BASELINE, seed=1, n_battles=2)


# ---- #483: per-owner selfplay concurrency rail (no PS server needed) ----


@pytest.mark.asyncio
async def test_concurrency_rail_rejects_when_owner_at_cap(tmp_path, monkeypatch):
    """A leaked battle token cannot spawn unbounded concurrent PS battles: when
    the owner already holds ARENA_MAX_BATTLES_PER_OWNER in-flight slots, the next
    selfplay call is rejected BEFORE any battle runs (no PS server reached)."""
    from agentdex_arena.consent import _normalize_owner

    monkeypatch.setenv("ARENA_MAX_BATTLES_PER_OWNER", "3")
    gw = _gateway(tmp_path)
    init_mcp(gw, lambda: None)
    token = _battle_token(gw)
    owner = _normalize_owner("eddie@oppie.xyz")
    gw._owner_inflight[owner] = 3  # owner already at the cap

    with pytest.raises(ValueError, match="too many concurrent"):
        await selfplay_battle(token, _CODEX, _BASELINE, seed=1, n_battles=2)
    assert gw._owner_inflight[owner] == 3  # the rejected call took no slot


@pytest.mark.asyncio
async def test_concurrency_rail_releases_slot_after_failure(tmp_path):
    """The reserved slot is released in a finally even when the battle fails (no
    PS server here), so a failed self-play call never leaks a slot."""
    from agentdex_arena.consent import _normalize_owner

    gw = _gateway(tmp_path)
    init_mcp(gw, lambda: None)
    token = _battle_token(gw)
    owner = _normalize_owner("eddie@oppie.xyz")
    gw._owner_inflight[owner] = 1  # one other call in flight

    # run_selfplay_battle has no PS server → opaque error, but the slot must release
    with pytest.raises(ValueError, match="arena error"):
        await selfplay_battle(token, _CODEX, _BASELINE, seed=1, n_battles=2)
    assert gw._owner_inflight[owner] == 1  # back to the pre-call count (no leak)


# ---- PS-gated: codex actually drives moves through the MCP tool ----


def _ps_available() -> bool:
    host = os.environ.get("ADX_PS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADX_PS_PORT", "8000"))
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _pokeenv() -> bool:
    try:
        import poke_env  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(
    not (_ps_available() and _pokeenv()),
    reason="needs a live PS server (ADX_PS_HOST/PORT) + poke-env",
)
@pytest.mark.asyncio
async def test_codex_drives_moves_through_selfplay_mcp_tool(tmp_path):
    gw = _gateway(tmp_path)
    init_mcp(gw, lambda: None)
    token = _battle_token(gw)
    result = await selfplay_battle(token, _CODEX, _BASELINE, seed=42, n_battles=4)
    raw = result["raw_dims"]
    assert raw["total_moves"] > 0  # the C1 codex adapter chose moves over MCP
    assert raw["n_battles"] == 4
    assert raw["illegal_moves"] == 0
    # the opponent label is derived from harness_b (un-spoofable), namespaced
    assert raw["opponent_baseline"] == "harness:rng"
    assert result["winner"] in ("a", "b", "draw")
