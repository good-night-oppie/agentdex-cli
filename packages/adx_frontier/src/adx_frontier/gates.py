"""Class-differentiated gate selection for PokeAgent measurement windows."""

import math
from typing import Literal

GateClass = Literal["live_adversarial", "static"]


def pokeagent_gate_class(
    *, community_opponents: int, total_opponents: int, minimum_community_share: float
) -> GateClass:
    """Select the measured gate class from the window's opponent mix (ADR-0015 D4a)."""
    counts = (community_opponents, total_opponents)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        raise ValueError("opponent counts must be integers")
    if community_opponents < 0 or total_opponents < 0 or community_opponents > total_opponents:
        raise ValueError("opponent counts must satisfy 0 <= community <= total")
    if (
        isinstance(minimum_community_share, bool)
        or not isinstance(minimum_community_share, int | float)
        or not math.isfinite(float(minimum_community_share))
        or not 0.0 <= float(minimum_community_share) <= 1.0
    ):
        raise ValueError("minimum community share must be finite and within [0, 1]")
    if total_opponents == 0:
        return "static"
    share = community_opponents / total_opponents
    return "live_adversarial" if share >= float(minimum_community_share) else "static"
