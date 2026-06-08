"""Pareto domination check.

Per ADR-0005, Pareto domination decides battle winners AND evolution
acceptance (a mutation is kept iff the new candidate dominates the
incumbent across all objectives).
"""

from __future__ import annotations

from agentdex_engine.modules.battles.result import Domination


def dominates(
    a_scores: dict[str, float],
    b_scores: dict[str, float],
    objectives: dict[str, str],
) -> Domination:
    """Determine if A Pareto-dominates B (or vice versa, or tie).

    A dominates B iff:
      - A is at least as good as B on EVERY objective, AND
      - A is strictly better on at least one objective.

    `objectives` maps {name: "maximize" | "minimize"}.

    Raises ValueError if scores are missing an objective key.
    """
    a_at_least_as_good = True
    a_strictly_better = False
    b_at_least_as_good = True
    b_strictly_better = False

    for name, direction in objectives.items():
        if name not in a_scores or name not in b_scores:
            raise ValueError(f"objective {name!r} missing from scores")

        a_val = a_scores[name]
        b_val = b_scores[name]

        if direction == "maximize":
            a_wins_obj = a_val > b_val
            b_wins_obj = b_val > a_val
            a_ge_b = a_val >= b_val
            b_ge_a = b_val >= a_val
        elif direction == "minimize":
            a_wins_obj = a_val < b_val
            b_wins_obj = b_val < a_val
            a_ge_b = a_val <= b_val
            b_ge_a = b_val <= a_val
        else:
            raise ValueError(
                f"objective {name!r} direction must be maximize|minimize, got {direction!r}"
            )

        if not a_ge_b:
            a_at_least_as_good = False
        if not b_ge_a:
            b_at_least_as_good = False
        if a_wins_obj:
            a_strictly_better = True
        if b_wins_obj:
            b_strictly_better = True

    if a_at_least_as_good and a_strictly_better:
        return Domination.A_DOMINATES
    if b_at_least_as_good and b_strictly_better:
        return Domination.B_DOMINATES
    return Domination.TIE
