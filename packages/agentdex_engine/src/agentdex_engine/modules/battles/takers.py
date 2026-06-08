"""TurnTaker stubs — who unblocks an agent at a stop signal.

PHASE-2 MVP impls return canned responses. PHASE-3 wires in real LLM
proposer (OrchestratorTurnTaker) and WebSocket prompt to UI (HumanTurnTaker).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentdex_engine.modules.battles.result import Move
from agentdex_engine.modules.battles.stops import StopReason, StopSignal


@runtime_checkable
class TurnTaker(Protocol):
    async def respond(
        self, side_id: str, stop: StopSignal, history: list[Move]
    ) -> str: ...


class OrchestratorTurnTaker:
    """Canned-response stub. PHASE-3 will wire in ionq.metaharness.proposer."""

    def __init__(self, default_response: str = "proceed") -> None:
        self.default_response = default_response

    async def respond(
        self, side_id: str, stop: StopSignal, history: list[Move]
    ) -> str:
        # MVP: just approve completion checks; for direction-needed, pick first option.
        if stop.reason == StopReason.COMPLETION_CHECK:
            return "approved"
        if stop.reason == StopReason.DIRECTION_NEEDED and stop.options:
            return stop.options[0]
        return self.default_response


class HumanTurnTaker:
    """Stub that returns hardcoded responses; PHASE-3 prompts via WebSocket."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or []
        self._idx = 0

    async def respond(
        self, side_id: str, stop: StopSignal, history: list[Move]
    ) -> str:
        if self._idx < len(self.responses):
            r = self.responses[self._idx]
            self._idx += 1
            return r
        # default: approve / proceed
        return "approved" if stop.reason == StopReason.COMPLETION_CHECK else "yes"
