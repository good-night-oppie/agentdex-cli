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
    _allow_switch,
    codex_context,
    select_codex_move,
)


class _Move:
    def __init__(self, mid: str, base_power: int):
        self.id = mid
        self.base_power = base_power


class _Switch:
    def __init__(self, species: str):
        self.species = species


class _Battle:
    def __init__(self, moves, force_switch=False, switches=None):
        self.available_moves = moves
        self.available_switches = switches or []
        self.active_pokemon = None
        self.force_switch = force_switch


class _ToolPolicy:
    def __init__(self, allow_switch=True):
        self.allow_switch = allow_switch


class _PolicyHarness:
    def __init__(self, allow_switch=True):
        self.tool_policy = _ToolPolicy(allow_switch)
        self.system_prompt = ""


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


def test_illegal_id_is_counted_via_on_illegal_before_fallback():
    """A decided id outside the legal moves invokes ``on_illegal`` (so the runner
    records raw_dims['illegal_moves'] → move_legibility) AND still substitutes a
    legal move — a live policy can't hallucinate an illegal id for free."""
    battle = _Battle([_Move("tackle", 40), _Move("eruption", 150)])
    calls = []
    chosen = select_codex_move(
        harness=None,
        battle=battle,
        decide=lambda h, c: "hyperbeam",  # illegal id
        on_illegal=lambda: calls.append(1),
    )
    assert calls == [1]  # the illegal decision was surfaced exactly once
    assert chosen in battle.available_moves  # ...and a legal move still substituted


def test_on_illegal_not_called_for_legal_or_abstaining_decisions():
    """Legal picks and an abstaining hook (decide -> None) are NOT illegal."""
    battle = _Battle([_Move("tackle", 40), _Move("eruption", 150)])
    calls = []
    select_codex_move(
        harness=None,
        battle=battle,
        decide=lambda h, c: "tackle",
        on_illegal=lambda: calls.append(1),
    )
    select_codex_move(
        harness=None, battle=battle, decide=lambda h, c: None, on_illegal=lambda: calls.append(1)
    )
    select_codex_move(
        harness=None, battle=battle, on_illegal=lambda: calls.append(1)
    )  # greedy default
    assert calls == []  # none of these proposed an illegal id


def test_codex_context_exposes_moves_with_power():
    battle = _Battle([_Move("eruption", 150), _Move("ember", 40)])
    ctx = codex_context(battle)
    assert ctx["available_moves"] == [
        {"id": "eruption", "base_power": 150},
        {"id": "ember", "base_power": 40},
    ]
    assert "force_switch" in ctx and "active_hp_fraction" in ctx


# ---- switch action space (PR #343 review #3440104476) ----


def test_codex_context_exposes_available_switches():
    battle = _Battle([_Move("ember", 40)], switches=[_Switch("blastoise"), _Switch("venusaur")])
    ctx = codex_context(battle)
    assert ctx["available_switches"] == [{"species": "blastoise"}, {"species": "venusaur"}]


def test_decide_can_choose_a_switch_by_species():
    """A switch-aware policy can pick a switch target by species — the order returned
    is the poke-env switch object (create_order makes it a switch)."""
    blastoise = _Switch("blastoise")
    battle = _Battle([_Move("ember", 40)], switches=[blastoise])
    chosen = select_codex_move(harness=None, battle=battle, decide=lambda h, c: "blastoise")
    assert chosen is blastoise


def test_forced_switch_greedy_picks_the_first_switch():
    """On a forced switch (KO: no moves, only switches) the greedy default chooses a
    switch instead of returning None → the runner's random fallback."""
    venusaur = _Switch("venusaur")
    battle = _Battle([], force_switch=True, switches=[venusaur, _Switch("snorlax")])
    chosen = select_codex_move(harness=None, battle=battle)  # greedy default
    assert chosen is venusaur


def test_forced_switch_live_policy_can_pick_a_switch():
    snorlax = _Switch("snorlax")
    battle = _Battle([], force_switch=True, switches=[_Switch("venusaur"), snorlax])
    chosen = select_codex_move(harness=None, battle=battle, decide=lambda h, c: "snorlax")
    assert chosen is snorlax


def test_no_moves_and_no_switches_returns_none():
    assert select_codex_move(harness=None, battle=_Battle([], switches=[])) is None


def test_illegal_id_matching_neither_move_nor_switch_is_counted():
    battle = _Battle([_Move("ember", 40)], switches=[_Switch("blastoise")])
    calls = []
    chosen = select_codex_move(
        harness=None,
        battle=battle,
        decide=lambda h, c: "charizard",  # neither a legal move id nor a legal switch
        on_illegal=lambda: calls.append(1),
    )
    assert calls == [1]
    assert chosen is battle.available_moves[0]  # substitutes a legal action


# ---- tool_policy.allow_switch gating (PR #348 review #3440344820) ----


def test_voluntary_switch_dropped_when_allow_switch_false():
    """A genome with allow_switch=False must NOT be able to voluntarily switch: the
    switch is not in the action space, so naming it is counted illegal + substituted."""
    battle = _Battle([_Move("ember", 40)], switches=[_Switch("blastoise")])
    ctx = codex_context(battle, allow_switch=False)
    assert ctx["available_switches"] == []  # voluntary switch not offered
    calls = []
    chosen = select_codex_move(
        harness=_PolicyHarness(allow_switch=False),
        battle=battle,
        decide=lambda h, c: "blastoise",  # tries to voluntarily switch
        on_illegal=lambda: calls.append(1),
    )
    assert calls == [1]  # rejected as illegal
    assert chosen is battle.available_moves[0]  # substituted a legal move


def test_voluntary_switch_allowed_when_allow_switch_true():
    blastoise = _Switch("blastoise")
    battle = _Battle([_Move("ember", 40)], switches=[blastoise])
    chosen = select_codex_move(
        harness=_PolicyHarness(allow_switch=True),
        battle=battle,
        decide=lambda h, c: "blastoise",
    )
    assert chosen is blastoise


def test_forced_switch_allowed_even_when_allow_switch_false():
    """A forced switch (KO: no moves) is always legal — allow_switch only governs
    VOLUNTARY switches."""
    venusaur = _Switch("venusaur")
    battle = _Battle([], force_switch=True, switches=[venusaur])
    chosen = select_codex_move(harness=_PolicyHarness(allow_switch=False), battle=battle)
    assert chosen is venusaur


# ---- allow_switch hardening (PR #350 review) ----


def test_allow_switch_reads_dict_wire_form():
    """#3440401892: the Contract-1 dict/wire harness must be honored — getattr on a
    dict silently returned the default True, defeating the gate."""
    assert _allow_switch({"tool_policy": {"allow_switch": False}}) is False
    assert _allow_switch({"tool_policy": {"allow_switch": True}}) is True
    assert _allow_switch({"tool_policy": {}}) is True  # unset → default allow
    assert _allow_switch({}) is True
    assert _allow_switch(None) is True


def test_voluntary_switch_dropped_for_dict_harness_with_allow_switch_false():
    battle = _Battle([_Move("ember", 40)], switches=[_Switch("blastoise")])
    calls = []
    chosen = select_codex_move(
        harness={"tool_policy": {"allow_switch": False}},  # wire form
        battle=battle,
        decide=lambda h, c: "blastoise",
        on_illegal=lambda: calls.append(1),
    )
    assert calls == [1]  # the wire-form policy gate now fires
    assert chosen is battle.available_moves[0]


def test_no_move_non_forced_turn_still_gates_voluntary_switch():
    """#3440401897: a no-move turn that is NOT a forced switch (force_switch=False)
    is a VOLUNTARY switch opportunity — allow_switch=False must still drop it, rather
    than treating every no-move turn as a mandatory KO switch."""
    battle = _Battle([], force_switch=False, switches=[_Switch("blastoise")])
    ctx = codex_context(battle, allow_switch=False)
    assert ctx["available_switches"] == []  # not offered — it's voluntary, not forced
    # nothing the policy allows is legal → defer to the caller's (policy-aware) fallback
    assert select_codex_move(harness=_PolicyHarness(allow_switch=False), battle=battle) is None


def test_no_move_forced_switch_keeps_switches():
    """The same no-move turn WITH force_switch=True is mandatory → switches kept."""
    blastoise = _Switch("blastoise")
    battle = _Battle([], force_switch=True, switches=[blastoise])
    ctx = codex_context(battle, allow_switch=False)
    assert ctx["available_switches"] == [{"species": "blastoise"}]
    assert select_codex_move(harness=_PolicyHarness(allow_switch=False), battle=battle) is blastoise


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
