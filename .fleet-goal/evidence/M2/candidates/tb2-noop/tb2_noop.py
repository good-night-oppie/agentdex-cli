"""Harbor custom no-op agent for M2 WU-9 ($0 genuine TB2 candidate-pipe leg).

Implements harbor 0.18.0 ``BaseAgent`` API (see
``.fleet-goal/evidence/M2/harbor-agent-api.md``). Performs no environment
actions — ``setup``/``run`` are immediate no-ops — so quality is honestly 0
against any real TB2 verifier. No LLM, no network, $0.
"""

from __future__ import annotations

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class Tb2NoopAgent(BaseAgent):
    """Local mirror of harbor's builtin ``NopAgent`` — no actions, no LLM."""

    SUPPORTS_WINDOWS: bool = True

    @staticmethod
    def name() -> str:
        return "tb2-noop"

    def version(self) -> str | None:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        return

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        # Honest no-op: leave context empty; verifier will score reward=0.
        del instruction, environment, context
        return
