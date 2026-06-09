"""Trajectory tree — checkpoints + branches.

Per ADR-0005, every stop in a battle is a checkpoint. Forking from a past
checkpoint creates a sibling branch. The MVP engine drives ONE leaf path
linearly; forking-from-past is a future engine feature.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from agentdex_engine.modules.battles.result import Move


class Checkpoint(BaseModel):
    """A point in a battle where state was snapshotted.

    `state_hash` keys into a CheckpointStore (helios CAS or SQLite blob).
    """

    id: str
    battle_id: str
    side_id: str
    parent_branch_id: str | None = Field(
        default=None,
        description="Branch that led to this checkpoint. None for root.",
    )
    state_hash: str = Field(description="Hash addressing the state blob in CheckpointStore.")
    move_index: int

    @staticmethod
    def compute_state_hash(state: dict[str, Any]) -> str:
        payload = json.dumps(state, sort_keys=True, default=str).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


class Branch(BaseModel):
    """One step from a checkpoint, decided by a TurnTaker."""

    id: str
    from_checkpoint_id: str
    to_checkpoint_id: str | None = Field(
        default=None, description="None until child checkpoint is created."
    )
    move: Move


class TrajectoryTree(BaseModel):
    """Container for all checkpoints + branches in one battle.

    MVP shape: linear chain per side (no forks yet). Tree storage is
    branch-aware so forking-from-past can be added later without schema migration.
    """

    battle_id: str
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    branches: list[Branch] = Field(default_factory=list)

    def add_checkpoint(self, cp: Checkpoint) -> None:
        self.checkpoints.append(cp)

    def add_branch(self, br: Branch) -> None:
        self.branches.append(br)

    def leaves_for_side(self, side_id: str) -> list[Checkpoint]:
        """Checkpoints for a side that have no outgoing branch."""
        outgoing_from = {br.from_checkpoint_id for br in self.branches}
        return [c for c in self.checkpoints if c.side_id == side_id and c.id not in outgoing_from]
