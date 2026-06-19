"""Multi-dimensional Pareto fitness for the self-play meta-harness (Contract 3).

``multi_dim_fitness(results)`` turns a list of held-out-baseline battle results
into the 5-dim Pareto vector bene's evaluator optimizes:

    { win_rate, elo, move_legibility, no_forfeit_exploit, turn_efficiency }

Two dimensions reward strength (``win_rate``, ``elo`` vs the held-out baselines);
three are anti-reward-hack guards that close the gaming vectors the design note
(``docs/references/2026-06-12-arena-fun-multidim-rewardhack-design.md``)
identifies — a harness must not be able to score high by:

  - ``move_legibility``    : spamming illegal / unreadable moves (legibility =
                             fraction of moves that were legal).
  - ``no_forfeit_exploit`` : farming wins via forfeits (own or opponent) instead
                             of actually winning the battle.
  - ``turn_efficiency``    : stalling games out to inflate some secondary metric
                             (efficiency decays as games run longer than target).

All five are pure functions of the Contract-2 ``BattleResult`` dicts — no
poke-env, no I/O — so the evaluator and its tests are deterministic and cheap.

Contract 2 (mirrored here as a duck-typed dict until Lane A1 lands its canonical
type; reconcile then). A ``BattleResult`` aggregates a candidate harness's
battles against ONE opponent:

    {
      "winner": "a" | "b" | "draw",          # informational
      "battles": [...],                        # per-battle detail (opaque here)
      "trace_path": "str",
      "raw_dims": {
        "opponent_baseline": "RandomPlayer",   # which held-out baseline (for Elo)
        "n_battles":   int,                    # battles played in this matchup
        "wins_a":      int,                    # candidate (side-a) wins
        "draws":       int,                    # drawn battles (default 0)
        "turns":       int,                    # total turns across the matchup
        "forfeits":    int,                    # battles decided by a forfeit
        "illegal_moves": int,                  # illegal/rejected move attempts
        "total_moves":   int,                  # all move decisions the candidate made
      }
    }
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, TypedDict

from adx_showdown.selfplay.baselines import ANCHOR_ELO

# Target turn count for a decisive battle: at/under this scores full
# turn_efficiency; longer games decay toward 0 (stalling penalty). gen9 singles
# decisive games are typically well under 20 turns; tunable per format.
DEFAULT_TARGET_TURNS = 20.0
# Default opponent rating when a result omits/uses an unrecognized baseline — the
# mid baseline anchor, so an unlabeled matchup neither inflates nor tanks Elo.
_DEFAULT_OPP_ELO = ANCHOR_ELO["MaxBasePowerPlayer"]
_ELO_SCALE = 400.0  # standard Elo logistic scale


class FitnessVector(TypedDict):
    win_rate: float
    elo: float
    move_legibility: float
    no_forfeit_exploit: float
    turn_efficiency: float


def _stat(raw: dict, key: str, default: float = 0.0) -> float:
    v = raw.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _n_battles(raw: dict) -> float:
    """Battles in a matchup — explicit ``n_battles``, else wins+losses+draws."""
    if "n_battles" in raw:
        return max(0.0, _stat(raw, "n_battles"))
    wins = _stat(raw, "wins_a")
    draws = _stat(raw, "draws")
    losses = _stat(raw, "losses_a", default=-1.0)
    if losses >= 0:
        return wins + draws + losses
    return wins + draws  # no losses field: can only see wins+draws


def _perf_rating(score: float, opp_elo: float) -> float:
    """FIDE-style performance rating from a win-probability vs one opponent
    rating: ``opp + 400·log10(S/(1-S))``. Score is clamped off {0,1} so a clean
    sweep / shutout yields a large-but-finite rating instead of ±inf."""
    eps = 1e-6
    s = min(1.0 - eps, max(eps, score))
    return opp_elo + _ELO_SCALE * math.log10(s / (1.0 - s))


def _empty_vector() -> FitnessVector:
    # No battles demonstrated → a zero vector, Pareto-dominated by any real
    # result. We deliberately do NOT default legibility/no-forfeit to 1.0: a
    # harness that played nothing has proven nothing (anti-vacuous).
    return {
        "win_rate": 0.0,
        "elo": 0.0,
        "move_legibility": 0.0,
        "no_forfeit_exploit": 0.0,
        "turn_efficiency": 0.0,
    }


def multi_dim_fitness(
    results: Sequence[Any],
    *,
    target_turns: float = DEFAULT_TARGET_TURNS,
    baseline_elos: dict[str, float] | None = None,
) -> FitnessVector:
    """Aggregate held-out-baseline ``BattleResult`` dicts into the Pareto vector.

    ``results`` is one entry per (candidate vs held-out baseline) matchup.
    ``baseline_elos`` overrides the anchor ratings (defaults to ``ANCHOR_ELO``).
    Returns all-zeros when no battles were played (vacuous — the caller's
    anti-vacuous gate, e.g. C2's ``battles_played > 0``, is the real guard).
    """
    elos = baseline_elos or ANCHOR_ELO

    total_battles = 0.0
    total_wins = 0.0  # wins + 0.5·draws (score)
    total_turns = 0.0
    total_forfeits = 0.0
    total_illegal = 0.0
    total_moves = 0.0
    # Per-matchup (score, opp_elo, weight) for the battle-weighted Elo.
    perf_terms: list[tuple[float, float, float]] = []

    for r in results:
        raw = (r.get("raw_dims") if isinstance(r, dict) else None) or {}
        n = _n_battles(raw)
        if n <= 0:
            continue
        wins = _stat(raw, "wins_a")
        draws = _stat(raw, "draws")
        score_sum = wins + 0.5 * draws

        total_battles += n
        total_wins += score_sum
        total_turns += _stat(raw, "turns")
        total_forfeits += _stat(raw, "forfeits")
        total_illegal += _stat(raw, "illegal_moves")
        total_moves += _stat(raw, "total_moves")

        opp = raw.get("opponent_baseline")
        opp_elo = elos.get(opp, _DEFAULT_OPP_ELO) if isinstance(opp, str) else _DEFAULT_OPP_ELO
        perf_terms.append((score_sum / n, opp_elo, n))

    if total_battles <= 0:
        return _empty_vector()

    win_rate = total_wins / total_battles

    # Battle-weighted average of the per-matchup performance ratings: beating a
    # stronger baseline contributes a higher rating, weighted by sample size.
    weight_sum = sum(w for _, _, w in perf_terms)
    elo = (
        sum(_perf_rating(s, o) * w for s, o, w in perf_terms) / weight_sum
        if weight_sum > 0
        else 0.0
    )

    # move_legibility: share of move decisions that were legal. No move data →
    # 0.0 (unproven), never a free 1.0.
    move_legibility = max(0.0, 1.0 - total_illegal / total_moves) if total_moves > 0 else 0.0

    # no_forfeit_exploit: share of battles decided on their merits, not a forfeit.
    no_forfeit_exploit = max(0.0, 1.0 - total_forfeits / total_battles)

    # turn_efficiency: 1.0 at/under target, decaying as the average game drags on
    # (stalling penalty). avg over ALL battles played.
    avg_turns = total_turns / total_battles
    turn_efficiency = min(1.0, target_turns / avg_turns) if avg_turns > 0 else 0.0

    return {
        "win_rate": win_rate,
        "elo": elo,
        "move_legibility": move_legibility,
        "no_forfeit_exploit": no_forfeit_exploit,
        "turn_efficiency": turn_efficiency,
    }


__all__ = ["FitnessVector", "multi_dim_fitness", "DEFAULT_TARGET_TURNS"]
