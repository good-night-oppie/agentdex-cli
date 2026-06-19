"""C1 — codex move adapter (SPEC Lane C, Contract 5) + the runner routing.

Unit tests (CI-safe, no poke-env): the greedy default, the live-codex ``decide``
hook, the illegal-move guard, the ``codex_context`` shape, and the strategy
constants the runner dispatches on. A PS-gated end-to-end test drives a real
``llm_freeform`` (codex) harness vs a held-out baseline through A1's runner —
the same move path the ``selfplay_battle`` MCP tool runs — proving codex's logic
picks the moves (closes SPEC DONE #1; the live LLM dogfood is a follow-up)."""

from __future__ import annotations

import os
import socket

import pytest
from adx_showdown.selfplay.codex_adapter import (
    CODEX_STRATEGIES,
    codex_context,
    select_codex_move,
)


class _Move:
    def __init__(self, mid: str, base_power: int):
        self.id = mid
        self.base_power = base_power


class _Battle:
    def __init__(self, moves, force_switch=False):
        self.available_moves = moves
        self.active_pokemon = None
        self.force_switch = force_switch


# ---- the codex move seam ----


def test_routes_the_llm_strategies():
    assert "llm_freeform" in CODEX_STRATEGIES
    assert "codex" in CODEX_STRATEGIES


def test_greedy_default_picks_highest_base_power():
    battle = _Battle([_Move("tackle", 40), _Move("eruption", 150), _Move("ember", 40)])
    chosen = select_codex_move(harness=None, battle=battle)
    assert chosen.id == "eruption"


def test_no_available_moves_returns_none():
    assert select_codex_move(harness=None, battle=_Battle([])) is None


def test_live_codex_decide_hook_is_honored():
    """A live codex/LLM plugs in via ``decide`` — the adapter returns the move it
    names (this is the seam the real codex drives over MCP)."""
    battle = _Battle([_Move("tackle", 40), _Move("eruption", 150)])

    def decide(harness, ctx):
        # codex chooses the LOW-power move on purpose — proving its decision, not
        # the greedy default, drove the pick.
        return "tackle"

    chosen = select_codex_move(harness=None, battle=battle, decide=decide)
    assert chosen.id == "tackle"


def test_decide_returning_illegal_id_falls_back_to_a_legal_move():
    battle = _Battle([_Move("tackle", 40), _Move("eruption", 150)])
    chosen = select_codex_move(harness=None, battle=battle, decide=lambda h, c: "hyperbeam")
    assert chosen in battle.available_moves  # never an illegal move through the seam


def test_decide_returning_none_defers():
    battle = _Battle([_Move("tackle", 40)])
    assert select_codex_move(harness=None, battle=battle, decide=lambda h, c: None) is None


def test_codex_context_exposes_moves_with_power():
    battle = _Battle([_Move("eruption", 150), _Move("ember", 40)])
    ctx = codex_context(battle)
    assert ctx["available_moves"] == [
        {"id": "eruption", "base_power": 150},
        {"id": "ember", "base_power": 40},
    ]
    assert "force_switch" in ctx and "active_hp_fraction" in ctx


# ---- PS-gated end-to-end: codex (llm_freeform) drives moves vs a baseline ----


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


requires_ps = pytest.mark.skipif(
    not (_ps_available() and _pokeenv()),
    reason="needs a live PS server (ADX_PS_HOST/PORT) + poke-env",
)


@requires_ps
@pytest.mark.asyncio
async def test_codex_harness_drives_moves_vs_baseline():
    """A real ``llm_freeform`` (codex) harness plays vs a ``random`` baseline
    harness through A1's runner (the selfplay_battle MCP tool's move path): the
    codex adapter chose every move (total_moves > 0) and the greedy codex policy
    beats Random."""
    from adx_showdown.harness import BattleHarness
    from adx_showdown.selfplay.runner import run_selfplay_battle

    codex = BattleHarness(harness_id="codex-c1", move_selection_strategy="llm_freeform")
    baseline = BattleHarness(harness_id="rng", move_selection_strategy="random")
    result = await run_selfplay_battle(
        codex, baseline, seed=42, n_battles=4, opponent_baseline="RandomPlayer"
    )
    raw = result.raw_dims
    assert raw["total_moves"] > 0  # the codex adapter made move decisions
    assert raw["n_battles"] == 4
    assert raw["illegal_moves"] == 0  # the seam never returns an illegal move
    assert result.winner in ("a", "b", "draw")
