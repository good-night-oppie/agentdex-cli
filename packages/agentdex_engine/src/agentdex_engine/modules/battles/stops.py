"""Stop signal contract — how agents say 'your turn'."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class StopReason(StrEnum):
    APPROVAL_NEEDED = "approval_needed"
    CLARIFICATION_NEEDED = "clarification_needed"
    DIRECTION_NEEDED = "direction_needed"
    COMPLETION_CHECK = "completion_check"
    BLOCKED = "blocked"


class StopSignal(BaseModel):
    reason: StopReason
    context: str = Field(description="What the agent was doing when it stopped.")
    options: list[str] | None = Field(
        default=None,
        description="Candidate next steps if reason=DIRECTION_NEEDED.",
    )
    proposed_completion: dict[str, Any] | None = Field(
        default=None,
        description="Final output payload if reason=COMPLETION_CHECK.",
    )
