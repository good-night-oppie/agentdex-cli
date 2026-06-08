from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ParetoPosition = Literal["dominated", "undominated", "no-clear-winner"] | int


class ResultCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expedition_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    pass_rate: float = Field(ge=0.0, le=1.0)
    cost_dollar: float = Field(ge=0.0)
    cost_token: int = Field(ge=0)
    speed_wall_clock_sec: float = Field(ge=0.0)
    failure_trace_path: str | None = None
    pareto_position: ParetoPosition
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
