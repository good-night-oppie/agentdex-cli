"""PokeAgent Challenge measurement contract (ADR-0015 D4a/D5/D6)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

from adx_frontier.candidate import AgentCandidate
from adx_frontier.gates import pokeagent_gate_class

from adx_ladders.base import LadderAdapter, LadderClass, MeasureResult, Receipt


@dataclass(frozen=True)
class PokeAgentResult:
    rating: float
    rating_ref: str
    community_opponents: int
    total_opponents: int
    wall_clock_sec: float
    cost_dollar: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.rating_ref, str) or not self.rating_ref.strip():
            raise ValueError("rating_ref must be a non-empty server receipt")
        numbers = (self.rating, self.wall_clock_sec, self.cost_dollar)
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in numbers
        ):
            raise ValueError("rating, wall-clock, and cost must be non-negative finite numbers")
        pokeagent_gate_class(
            community_opponents=self.community_opponents,
            total_opponents=self.total_opponents,
            minimum_community_share=0.0,
        )


class PokeAgentAdapter(LadderAdapter):
    ladder_id = "pokeagent-gen1ou"
    ladder_class = LadderClass.LIVE_ADVERSARIAL

    def __init__(
        self,
        run_window: Callable[[AgentCandidate, float], PokeAgentResult],
        *,
        minimum_community_share: float,
    ) -> None:
        self._run_window = run_window
        self._minimum_community_share = minimum_community_share

    def measure(self, candidate: AgentCandidate) -> MeasureResult:
        self.pre_run_check(candidate)
        window = self._run_window(candidate, candidate.budget.wall_clock_min * 60.0)
        effective = LadderClass(
            pokeagent_gate_class(
                community_opponents=window.community_opponents,
                total_opponents=window.total_opponents,
                minimum_community_share=self._minimum_community_share,
            )
        )
        return MeasureResult(
            scores={
                "quality": window.rating,
                "cost_dollar": window.cost_dollar,
                "wall_clock_sec": window.wall_clock_sec,
            },
            receipt=Receipt(tier="verified", kind="pokeagent_rating", ref=window.rating_ref),
            ladder_id=self.ladder_id,
            base_model=candidate.base_model,
            budget_usd=candidate.budget.usd,
            budget_wall_clock_min=candidate.budget.wall_clock_min,
            cost_is_measured=True,
            effective_ladder_class=effective,
        )
