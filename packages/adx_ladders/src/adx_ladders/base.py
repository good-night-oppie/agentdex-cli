"""LadderAdapter ABC + measurement receipt types (ADR-0015 D3/D4/D6).

Adapters MUST run the candidate out-of-process (ADR D3): hour-scale ladder
runs are incompatible with bene's in-process evaluator. Enforcement of the
out-of-process boundary is per-adapter; this module only defines the contract.
"""

from __future__ import annotations

import abc
import enum
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from adx_frontier.candidate import FRONTIER_AXES, AgentCandidate


class LadderClass(enum.Enum):
    """Two-class ladder taxonomy (ADR-0015 D4)."""

    LIVE_ADVERSARIAL = "live_adversarial"
    STATIC = "static"


@dataclass(frozen=True)
class Receipt:
    """Two-tier trust receipt (ADR-0015 D6).

    ``verified`` requires a non-empty third-party ``ref`` (scorecard ID,
    submission ID, server-side rating). ``self_reported`` requires a non-empty
    ``artifacts`` tuple (eval logs, transcripts, lineage JSON).
    """

    tier: str
    kind: str
    ref: str
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.tier not in ("verified", "self_reported"):
            raise ValueError(f"tier must be 'verified' or 'self_reported' (got {self.tier!r})")
        if self.tier == "verified" and not str(self.ref).strip():
            raise ValueError("tier 'verified' requires a non-empty ref")
        if self.tier == "self_reported":
            if not self.artifacts or not any(str(a).strip() for a in self.artifacts):
                raise ValueError("tier 'self_reported' requires a non-empty artifacts tuple")


@dataclass(frozen=True)
class MeasureResult:
    """Score dict + receipt emitted by a ladder adapter at a declared budget.

    ``cost_is_measured`` is honesty metadata (not a frontier axis): True only
    when ``scores["cost_dollar"]`` came from a real/injected measurement.
    Defaults to False so a missing flag cannot accidentally claim honesty
    when adapters fall back to ``budget.usd``.
    """

    scores: Mapping[str, float]
    receipt: Receipt
    ladder_id: str
    base_model: str
    budget_usd: float
    budget_wall_clock_min: float
    cost_is_measured: bool = False
    effective_ladder_class: LadderClass | None = None

    def __post_init__(self) -> None:
        if self.effective_ladder_class is not None and not isinstance(
            self.effective_ladder_class, LadderClass
        ):
            raise ValueError("effective_ladder_class must be a LadderClass")
        expected = set(FRONTIER_AXES)
        got = set(self.scores)
        if got != expected:
            raise ValueError(f"scores keys must be exactly {FRONTIER_AXES}; got {sorted(got)}")
        validated: dict[str, float] = {}
        for key, value in self.scores.items():
            # bool is a subclass of int — reject it explicitly.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"score {key!r} must be a finite float; got {value!r}")
            fval = float(value)
            if not math.isfinite(fval):
                raise ValueError(f"score {key!r} must be a finite float; got {value!r}")
            if key in ("cost_dollar", "wall_clock_sec") and fval < 0.0:
                raise ValueError(f"score {key!r} must be non-negative; got {value!r}")
            validated[key] = fval
        for key, value in (
            ("budget_usd", self.budget_usd),
            ("budget_wall_clock_min", self.budget_wall_clock_min),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(f"{key} must be a finite float > 0; got {value!r}")
        object.__setattr__(self, "scores", MappingProxyType(validated))


class LadderAdapter(abc.ABC):
    """Abstract ladder measurement adapter.

    Subclasses set ``ladder_id`` / ``ladder_class`` and implement ``measure``.
    Callers should invoke ``pre_run_check`` before ``measure``. Adapters MUST
    execute the candidate out-of-process (ADR D3); this base class documents
    the invariant — each concrete adapter enforces it.
    """

    ladder_id: str
    ladder_class: LadderClass

    def pre_run_check(self, candidate: AgentCandidate) -> None:
        """Validate candidate and confirm this ladder is in its declared set."""
        candidate.validate()
        if self.ladder_id not in candidate.ladders:
            raise ValueError(
                f"ladder {self.ladder_id!r} not in candidate.ladders={list(candidate.ladders)}"
            )

    @abc.abstractmethod
    def measure(self, candidate: AgentCandidate) -> MeasureResult:
        """Run the candidate on this ladder; return scores + receipt."""
