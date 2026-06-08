"""Agent domain models — Agent identity, versions, lineage."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AutonomyPolicy(StrEnum):
    """How aggressive an agent is about pausing for human input.

    See ADR-0005 §Per-stop UX.
    """

    LENIENT = "lenient"          # proposer handles most stops, human only high-risk
    CAUTIOUS = "cautious"        # human handles most, proposer only trivial
    FULL_AUTO = "full_auto"      # proposer always (cron /loop pattern)
    FULL_MANUAL = "full_manual"  # human always


class AgentVersion(BaseModel):
    """One product-facing snapshot of an agent.

    Bridges to Bene resource commits once Bene exists. For MVP, harness_blob is
    still the local runner scaffold, not the long-term unit of evolution.
    """

    id: str
    name: str
    parent_id: str | None = Field(
        default=None, description="Previous version this evolved from."
    )
    harness_blob: str = Field(
        description="Agent source (Python module text OR config JSON for declarative agents)."
    )
    evolution_commit_id: str | None = Field(
        default=None,
        description="Bene EvolutionCommit or equivalent resource-version snapshot.",
    )
    resource_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Exact resource_id -> version map backing this agent version.",
    )
    autonomy_policy: AutonomyPolicy = AutonomyPolicy.FULL_AUTO
    metadata: dict[str, Any] = Field(default_factory=dict)
