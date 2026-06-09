"""Pareto verdict — pick a winner across ResultCards on (pass_rate ↑, cost ↓, speed ↓).

Domination: agent A dominates B iff A ≥ B on every objective AND > on at least
one. Single non-dominated agent = winner; multiple non-dominated = ``no_clear_winner``.

This module wraps :func:`agentdex_engine.modules.evolver.pareto.dominates` to
keep the existing implementation as the single source of truth.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentdex_engine.cards import ResultCard
from agentdex_engine.modules.battles.result import Domination
from agentdex_engine.modules.evolver.pareto import dominates

VerdictKind = Literal["dominated", "undominated", "no_clear_winner"]


OBJECTIVES = {
    "pass_rate": "maximize",
    "cost_dollar": "minimize",
    "speed_wall_clock_sec": "minimize",
}


class ParetoVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    winner: str | None
    verdict_kind: VerdictKind
    rankings: dict[str, dict[str, int]] = Field(default_factory=dict)


def _is_failed(rc: ResultCard) -> bool:
    """Card is excluded from Pareto verdict when it has no comparable cost
    signal — currently triggered by ``_failed_baseline_record`` setting
    ``cost_dollar=None`` + ``failure_trace_path != None`` (MF5, 2026-06-09).
    """
    return rc.cost_dollar is None or rc.failure_trace_path is not None


def _scores(rc: ResultCard) -> dict[str, float]:
    # Only called on eligible (non-failed) cards; cost_dollar guaranteed non-None.
    assert rc.cost_dollar is not None
    return {
        "pass_rate": float(rc.pass_rate),
        "cost_dollar": float(rc.cost_dollar),
        "speed_wall_clock_sec": float(rc.speed_wall_clock_sec),
    }


def _rank_within(values: list[tuple[str, float]], *, ascending: bool) -> dict[str, int]:
    ordered = sorted(values, key=lambda kv: (kv[1] if ascending else -kv[1]))
    return {agent_id: idx + 1 for idx, (agent_id, _) in enumerate(ordered)}


def _rankings_for(cards: list[ResultCard]) -> dict[str, dict[str, int]]:
    # Rank only eligible cards; failed baselines are surfaced via the
    # EvolutionCard's repair seeds + failure_trace_path on the ResultCard.
    eligible = [c for c in cards if not _is_failed(c)]
    by_pass = _rank_within([(c.agent_id, c.pass_rate) for c in eligible], ascending=False)
    by_cost = _rank_within(
        [(c.agent_id, float(c.cost_dollar)) for c in eligible if c.cost_dollar is not None],
        ascending=True,
    )
    by_speed = _rank_within(
        [(c.agent_id, c.speed_wall_clock_sec) for c in eligible], ascending=True
    )
    return {
        c.agent_id: {
            "pass_rate": by_pass[c.agent_id],
            "cost_dollar": by_cost[c.agent_id],
            "speed_wall_clock_sec": by_speed[c.agent_id],
        }
        for c in eligible
    }


def pareto_verdict(result_cards: list[ResultCard]) -> ParetoVerdict:
    """Identify the Pareto winner or surface ``no_clear_winner`` / ``dominated``.

    Failed-baseline ResultCards (``cost_dollar=None`` or
    ``failure_trace_path`` set) are EXCLUDED from the verdict pool — a crash
    is not "cheapest". If the eligible pool has 0 cards → ``no_clear_winner``;
    1 card → that baseline wins by default (undominated); ≥2 → standard
    Pareto domination.
    """
    if not result_cards:
        return ParetoVerdict(winner=None, verdict_kind="no_clear_winner")

    eligible = [c for c in result_cards if not _is_failed(c)]
    if not eligible:
        return ParetoVerdict(winner=None, verdict_kind="no_clear_winner")

    if len(eligible) == 1:
        only = eligible[0]
        return ParetoVerdict(
            winner=only.agent_id,
            verdict_kind="undominated",
            rankings=_rankings_for(result_cards),
        )

    rankings = _rankings_for(result_cards)
    scores = {c.agent_id: _scores(c) for c in eligible}

    non_dominated_ids: list[str] = []
    for candidate in eligible:
        cand_id = candidate.agent_id
        dominated_by_someone = False
        for other in eligible:
            if other.agent_id == cand_id:
                continue
            verdict = dominates(scores[other.agent_id], scores[cand_id], OBJECTIVES)
            if verdict == Domination.A_DOMINATES:
                dominated_by_someone = True
                break
        if not dominated_by_someone:
            non_dominated_ids.append(cand_id)

    if len(non_dominated_ids) == 1:
        return ParetoVerdict(
            winner=non_dominated_ids[0],
            verdict_kind="undominated",
            rankings=rankings,
        )

    return ParetoVerdict(
        winner=None,
        verdict_kind="no_clear_winner",
        rankings=rankings,
    )
