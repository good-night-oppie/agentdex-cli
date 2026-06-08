"""Task domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScorerSpec(BaseModel):
    """Identifies which Scorer impl to use + its config."""

    name: str
    objectives: dict[str, str] = Field(
        description="{objective_name: 'maximize' | 'minimize'}",
    )
    config: dict[str, Any] = Field(default_factory=dict)


class TaskContext(BaseModel):
    """Everything an agent needs to attempt a task.

    Real-task init (PHASE-3 MCP) populates this from the human's current
    session state. MVP (this PHASE-2 slice) populates from CLI / fixtures.
    """

    id: str
    title: str
    description: str
    expected_output: str | None = Field(
        default=None,
        description="Optional canonical answer (used by exact-match scorers).",
    )
    expects_human: bool = Field(
        default=False,
        description="If true, COLLAB-mode battles allowed; else AUTONOMOUS-only.",
    )
    scorer: ScorerSpec
    config: dict[str, Any] = Field(default_factory=dict)
