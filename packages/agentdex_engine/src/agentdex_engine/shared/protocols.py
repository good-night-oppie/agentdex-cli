"""Shared Protocol interfaces used across modules.

These are runtime-checkable Protocols. Implementations live in their
respective module dirs (modules/agents/, modules/tasks/, modules/evolver/).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentdex_engine.modules.battles.result import Move
    from agentdex_engine.modules.battles.stops import StopSignal
    from agentdex_engine.modules.tasks.models import TaskContext


@runtime_checkable
class AgentRunner(Protocol):
    """Drives a single agent's execution within one side of a battle.

    The runner produces work until it must yield (a stop signal). The engine
    then routes the stop to a TurnTaker, gets a response, and calls resume.
    """

    async def run_until_stop(
        self, task: TaskContext, history: list[Move]
    ) -> AgentTurnOutput: ...

    def resume(self, taker_response: str) -> None: ...

    @property
    def final_output(self) -> str | None:
        """Set when the agent has terminated. None otherwise."""
        ...


@runtime_checkable
class Scorer(Protocol):
    """Scores an agent's final output against a task. Returns per-objective values."""

    def score(self, task: TaskContext, agent_output: str) -> dict[str, float]: ...

    @property
    def objectives(self) -> dict[str, str]:
        """{objective_name: 'maximize' | 'minimize'}."""
        ...


@runtime_checkable
class Mutator(Protocol):
    """Proposes a new agent candidate from an existing one + battle history."""

    async def propose(
        self, parent_version_id: str, battle_history: list[Move]
    ) -> AgentCandidate: ...


# Returned by AgentRunner.run_until_stop. Defined here to avoid a circular
# import; concrete usage lives in the engine.
class AgentTurnOutput:
    __slots__ = ("output_text", "stop_signal", "is_terminal")

    def __init__(
        self,
        output_text: str,
        stop_signal: StopSignal | None,
        is_terminal: bool,
    ) -> None:
        self.output_text = output_text
        self.stop_signal = stop_signal
        self.is_terminal = is_terminal


# Placeholder so Mutator Protocol typechecks. Real AgentCandidate lives in
# modules/agents/models.py once evolver is wired.
class AgentCandidate:
    __slots__ = ("source_code", "metadata")

    def __init__(self, source_code: str, metadata: dict[str, Any]) -> None:
        self.source_code = source_code
        self.metadata = metadata
