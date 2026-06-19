"""Tests for A3 — multi_dim_fitness (Contract 3) + held-out baselines.

The anti-reward-hack tests are the heart of this lane: a harness must NOT be able
to score well by forfeit-farming, illegal-move spam, or stalling. Each gaming
vector is asserted to tank its guard dimension while honest strong play scores
high across the board."""

from __future__ import annotations

import math

import pytest
from adx_showdown.selfplay.baselines import (
    ANCHOR_ELO,
    MAX_BASE_POWER_PLAYER,
    RANDOM_PLAYER,
    SIMPLE_HEURISTICS_PLAYER,
    anchor_elo,
    baseline_names,
    build_baseline,
    max_base_power_choice,
)
from adx_showdown.selfplay.fitness import multi_dim_fitness


def _result(
    *,
    opponent=RANDOM_PLAYER,
    n_battles=30,
    wins_a=15,
    draws=0,
    turns=None,
    forfeits=0,
    illegal_moves=0,
    total_moves=None,
):
    if turns is None:
        turns = n_battles * 12  # ~12 turns/battle by default
    if total_moves is None:
        total_moves = turns  # one move decision per turn by default
    return {
        "winner": "a" if wins_a * 2 >= n_battles else "b",
        "battles": [],
        "trace_path": "/tmp/trace.json",
        "raw_dims": {
            "opponent_baseline": opponent,
            "n_battles": n_battles,
            "wins_a": wins_a,
            "draws": draws,
            "turns": turns,
            "forfeits": forfeits,
            "illegal_moves": illegal_moves,
            "total_moves": total_moves,
        },
    }


# ---- baselines registry ----


def test_three_held_out_baselines_in_difficulty_order():
    assert baseline_names() == [RANDOM_PLAYER, MAX_BASE_POWER_PLAYER, SIMPLE_HEURISTICS_PLAYER]
    assert (
        anchor_elo(RANDOM_PLAYER)
        < anchor_elo(MAX_BASE_POWER_PLAYER)
        < anchor_elo(SIMPLE_HEURISTICS_PLAYER)
    )


def test_anchor_elo_unknown_raises():
    with pytest.raises(KeyError):
        anchor_elo("GrandmasterPlayer")


def test_max_base_power_choice_picks_highest_power():
    class M:
        def __init__(self, p):
            self.base_power = p

    moves = [M(40), M(120), M(90)]
    assert max_base_power_choice(moves).base_power == 120


def test_max_base_power_choice_handles_none_power_and_empty():
    class M:
        def __init__(self, p):
            self.base_power = p

    assert max_base_power_choice([]) is None
    assert max_base_power_choice(None) is None
    # status move with base_power None counts as 0, attack wins
    assert max_base_power_choice([M(None), M(60)]).base_power == 60


def test_build_baseline_unknown_name_raises():
    with pytest.raises(KeyError):
        build_baseline("NopePlayer")


def test_build_baseline_without_pokeenv_raises_runtime():
    # poke-env is intentionally absent from the fitness env; building a live
    # player must fail with a clear, actionable error (not ModuleNotFoundError).
    if _pokeenv_installed():
        pytest.skip("poke-env installed in this env")
    with pytest.raises(RuntimeError, match="poke-env"):
        build_baseline(RANDOM_PLAYER)


def _pokeenv_installed() -> bool:
    try:
        import poke_env  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


# ---- fitness: shape + strong play ----


def test_returns_all_five_dimensions():
    fit = multi_dim_fitness([_result()])
    assert set(fit) == {
        "win_rate",
        "elo",
        "move_legibility",
        "no_forfeit_exploit",
        "turn_efficiency",
    }


def test_win_rate_aggregates_across_baselines():
    # 30 wins / 30 vs Random, 15/30 vs MaxBP, 6/30 vs Heuristic = 51/90
    results = [
        _result(opponent=RANDOM_PLAYER, n_battles=30, wins_a=30),
        _result(opponent=MAX_BASE_POWER_PLAYER, n_battles=30, wins_a=15),
        _result(opponent=SIMPLE_HEURISTICS_PLAYER, n_battles=30, wins_a=6),
    ]
    assert multi_dim_fitness(results)["win_rate"] == pytest.approx(51 / 90)


def test_draws_count_half():
    fit = multi_dim_fitness([_result(n_battles=10, wins_a=4, draws=2)])
    assert fit["win_rate"] == pytest.approx((4 + 1.0) / 10)


def test_strong_legal_decisive_play_scores_high_everywhere():
    results = [
        _result(opponent=RANDOM_PLAYER, n_battles=30, wins_a=28, turns=30 * 10),
        _result(opponent=MAX_BASE_POWER_PLAYER, n_battles=30, wins_a=24, turns=30 * 11),
    ]
    fit = multi_dim_fitness(results)
    assert fit["win_rate"] > 0.8
    assert fit["move_legibility"] == 1.0
    assert fit["no_forfeit_exploit"] == 1.0
    assert fit["turn_efficiency"] == 1.0  # ~10-11 turns < 20 target
    assert fit["elo"] > anchor_elo(MAX_BASE_POWER_PLAYER)  # beats strong baseline handily


# ---- elo ----


def test_elo_50pct_vs_baseline_equals_anchor():
    # exactly 50% vs MaxBasePower → performance rating == that anchor
    fit = multi_dim_fitness([_result(opponent=MAX_BASE_POWER_PLAYER, n_battles=100, wins_a=50)])
    assert fit["elo"] == pytest.approx(ANCHOR_ELO[MAX_BASE_POWER_PLAYER], abs=1e-6)


def test_elo_beating_stronger_baseline_rates_higher():
    weak = multi_dim_fitness([_result(opponent=RANDOM_PLAYER, n_battles=100, wins_a=75)])
    strong = multi_dim_fitness(
        [_result(opponent=SIMPLE_HEURISTICS_PLAYER, n_battles=100, wins_a=75)]
    )
    assert strong["elo"] > weak["elo"]  # same 75% but vs a higher-anchored opp


def test_elo_finite_on_clean_sweep():
    fit = multi_dim_fitness([_result(opponent=RANDOM_PLAYER, n_battles=30, wins_a=30)])
    assert math.isfinite(fit["elo"])


# ---- anti-reward-hack: each gaming vector tanks its guard ----


def test_forfeit_farming_tanks_no_forfeit_exploit():
    # "wins" but every battle was a forfeit → no_forfeit_exploit → 0
    fit = multi_dim_fitness([_result(n_battles=30, wins_a=30, forfeits=30)])
    assert fit["no_forfeit_exploit"] == 0.0
    # half forfeits → 0.5
    fit2 = multi_dim_fitness([_result(n_battles=30, wins_a=30, forfeits=15)])
    assert fit2["no_forfeit_exploit"] == pytest.approx(0.5)


def test_illegal_move_spam_tanks_legibility():
    # 300 illegal of 300 moves → legibility 0
    fit = multi_dim_fitness([_result(n_battles=30, wins_a=30, total_moves=300, illegal_moves=300)])
    assert fit["move_legibility"] == 0.0
    # 30 illegal of 300 → 0.9
    fit2 = multi_dim_fitness([_result(n_battles=30, wins_a=30, total_moves=300, illegal_moves=30)])
    assert fit2["move_legibility"] == pytest.approx(0.9)


def test_stalling_tanks_turn_efficiency():
    # average 200 turns/battle vs 20 target → efficiency 0.1
    fit = multi_dim_fitness([_result(n_battles=10, wins_a=10, turns=2000)])
    assert fit["turn_efficiency"] == pytest.approx(0.1)


def test_winrate_high_but_hacked_play_is_pareto_dominated():
    """A forfeit-farming + stalling harness with 100% win_rate must NOT dominate
    honest play: its anti-reward-hack dims are strictly worse, so Pareto keeps
    both — the gaming harness can't sweep the frontier on win_rate alone."""
    honest = multi_dim_fitness(
        [_result(n_battles=30, wins_a=24, turns=30 * 10, forfeits=0, illegal_moves=0)]
    )
    hacked = multi_dim_fitness(
        [_result(n_battles=30, wins_a=30, turns=30 * 150, forfeits=30, illegal_moves=200)]
    )
    assert hacked["win_rate"] > honest["win_rate"]  # hacked "wins" more
    # ...but loses on every guard dimension
    assert hacked["no_forfeit_exploit"] < honest["no_forfeit_exploit"]
    assert hacked["move_legibility"] < honest["move_legibility"]
    assert hacked["turn_efficiency"] < honest["turn_efficiency"]


# ---- edge cases ----


def test_empty_results_is_zero_vector():
    assert multi_dim_fitness([]) == {
        "win_rate": 0.0,
        "elo": 0.0,
        "move_legibility": 0.0,
        "no_forfeit_exploit": 0.0,
        "turn_efficiency": 0.0,
    }


def test_zero_battle_results_are_skipped_as_vacuous():
    assert multi_dim_fitness([_result(n_battles=0, wins_a=0)]) == multi_dim_fitness([])


def test_no_move_data_gives_zero_legibility_not_free_one():
    r = _result(n_battles=10, wins_a=10, total_moves=0, illegal_moves=0)
    assert multi_dim_fitness([r])["move_legibility"] == 0.0


def test_missing_opponent_label_uses_default_elo_not_crash():
    r = _result(n_battles=20, wins_a=10)
    del r["raw_dims"]["opponent_baseline"]
    fit = multi_dim_fitness([r])
    assert math.isfinite(fit["elo"])
