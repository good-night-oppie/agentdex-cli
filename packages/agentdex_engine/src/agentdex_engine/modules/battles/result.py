"""Battle Move + Result models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agentdex_engine.modules.battles.stops import StopSignal


class Move(BaseModel):
    """One stop-resume cycle for one side."""

    side_id: str
    turn_index: int
    stop: StopSignal
    taker_response: str
    agent_output_text: str = Field(description="What the agent emitted up to the stop.")


class Domination(StrEnum):
    A_DOMINATES = "a_dominates"
    B_DOMINATES = "b_dominates"
    TIE = "tie"


class SideResult(BaseModel):
    side_id: str
    agent_version_id: str
    final_output: str
    scores: dict[str, float]
    move_count: int
    elapsed_s: float


class BattleResult(BaseModel):
    battle_id: str
    task_id: str
    side_a: SideResult
    side_b: SideResult
    winner: Domination
    objectives: dict[str, str] = Field(
        description="From the task's ScorerSpec; needed to interpret scores."
    )
