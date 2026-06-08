"""Trivial agent implementations for end-to-end smoke testing.

These satisfy the AgentRunner Protocol. Each runs through exactly two
phases: emit a COMPLETION_CHECK stop (asking taker to confirm done), then
on resume mark terminal with a final output derived from task description.
"""

from __future__ import annotations

from agentdex_engine.modules.battles.result import Move
from agentdex_engine.modules.battles.stops import StopReason, StopSignal
from agentdex_engine.modules.tasks.models import TaskContext
from agentdex_engine.shared.protocols import AgentTurnOutput


class _BaseTrivialAgent:
    def __init__(self) -> None:
        self._stage = "init"
        self._final: str | None = None
        self._pending_resume = False

    @property
    def final_output(self) -> str | None:
        return self._final

    def _transform(self, text: str) -> str:
        raise NotImplementedError

    async def run_until_stop(
        self, task: TaskContext, history: list[Move]
    ) -> AgentTurnOutput:
        if self._stage == "init":
            self._stage = "awaiting_approval"
            self._pending_resume = True
            proposed = self._transform(task.description)
            return AgentTurnOutput(
                output_text=f"I propose: {proposed!r}",
                stop_signal=StopSignal(
                    reason=StopReason.COMPLETION_CHECK,
                    context="ready to commit final answer",
                    proposed_completion={"output": proposed},
                ),
                is_terminal=False,
            )
        if self._stage == "awaiting_approval":
            # resume was called; commit the answer
            self._final = self._transform(task.description)
            self._stage = "done"
            return AgentTurnOutput(
                output_text=f"Committed: {self._final!r}",
                stop_signal=None,
                is_terminal=True,
            )
        raise RuntimeError(f"agent already terminal: stage={self._stage}")

    def resume(self, taker_response: str) -> None:
        if not self._pending_resume:
            raise RuntimeError("resume called without pending stop")
        self._pending_resume = False
        # taker_response unused in MVP — agent commits regardless of approval


class EchoAgent(_BaseTrivialAgent):
    """v1: emits the input description unchanged."""

    def _transform(self, text: str) -> str:
        return text


class UppercaseAgent(_BaseTrivialAgent):
    """v2: uppercases the input description."""

    def _transform(self, text: str) -> str:
        return text.upper()


AGENT_REGISTRY = {
    "echo_agent_v1": EchoAgent,
    "echo_agent_v2": UppercaseAgent,
}


def make_agent(name: str) -> _BaseTrivialAgent:
    try:
        cls = AGENT_REGISTRY[name]
    except KeyError as e:
        raise KeyError(
            f"unknown agent {name!r}, known: {sorted(AGENT_REGISTRY)}"
        ) from e
    return cls()
