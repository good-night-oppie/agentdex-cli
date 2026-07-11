"""PokeAgent Challenge measurement contract (ADR-0015 D4a/D5/D6)."""

import math
from dataclasses import dataclass

from adx_frontier.gates import pokeagent_gate_class


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
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in numbers
        ):
            raise ValueError("rating, wall-clock, and cost must be non-negative finite numbers")
        pokeagent_gate_class(community_opponents=self.community_opponents, total_opponents=self.total_opponents, minimum_community_share=0.0)
