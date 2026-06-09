from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# C5 (workflow w0z1i9vcs follow-up): `excluded-failed` makes the
# pareto-pool exclusion that MF5 introduced explicit in the persisted
# YAML. Previously a crashed baseline was relabeled `dominated` even
# though pareto_verdict never compared it — downstream readers (Repair
# Oracle, lineage logs, audit tooling) could not distinguish "lost on
# Pareto" from "crashed and was excluded".
ParetoPosition = (
    Literal["dominated", "undominated", "no-clear-winner", "excluded-failed"]
    | int
)


class ResultCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expedition_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    pass_rate: float = Field(ge=0.0, le=1.0)
    # MF5 (harness-praxis tracer follow-up, 2026-06-09): allow None so a
    # crashed baseline ships a degraded card WITHOUT a $1e-6 floor that the
    # Pareto judge would mistake for "cheapest". Pareto's _scores() now
    # filters None costs out of the cost-axis ranking; the Repair Oracle
    # surfaces the failure as a structural seed via failure_trace_path.
    cost_dollar: float | None = Field(default=None, ge=0.0)
    cost_token: int | None = Field(default=None, ge=0)
    speed_wall_clock_sec: float = Field(ge=0.0)
    failure_trace_path: str | None = None
    pareto_position: ParetoPosition
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
