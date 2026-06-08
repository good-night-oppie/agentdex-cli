"""Oracle Protocol + OracleVerdict pydantic schema.

Three kinds (per phase-6 spec + ADR-0009 §Q5):
- ``hard``: regex-anchored number / provenance check, deterministic
- ``soft``: LLM-as-judge narrative coherence score, calibrated per
  ``oracle/calibration.py``
- ``repair``: meta-Oracle flag — surfaces weak rubrics as mutation seeds

OracleChain composes multiple Oracles into a single ``evaluate()`` call.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agentdex_engine.cards import TaskCard

OracleKind = Literal["hard", "soft", "repair"]


class OracleVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: OracleKind
    pass_: bool = Field(alias="pass")
    score: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)
    uncertainty: float | None = Field(default=None, ge=0.0, le=1.0)


OracleVerdictMap = dict[str, OracleVerdict]


@runtime_checkable
class Oracle(Protocol):
    """Evaluate a raw bridge response into one or more named verdicts.

    The returned dict's keys are dotted verdict names
    (e.g. ``"hard.revenue_total"``, ``"soft.narrative_coherence"``) and the
    values are OracleVerdict instances.
    """

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap: ...


class OracleChain:
    """Compose oracles; merge their verdict maps key-namespaced by oracle name."""

    def __init__(self, oracles: dict[str, Oracle]):
        self._oracles = oracles

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap:
        out: OracleVerdictMap = {}
        for name, oracle in self._oracles.items():
            sub = oracle.evaluate(response, task_card)
            for key, verdict in sub.items():
                ns_key = f"{name}.{key}" if not key.startswith(name) else key
                out[ns_key] = verdict
        return out

    @property
    def oracles(self) -> dict[str, Oracle]:
        return dict(self._oracles)
