"""agentdex_engine — Three Cards + Oracle + Pareto + battles/modules.

Public surface:
- TaskCard, ResultCard, EvolutionCard, Seed from `agentdex_engine.cards`
- (post-P6) Oracle protocol + hard/soft/repair implementations from `agentdex_engine.oracle`
- (post-P6) pareto_verdict, ParetoVerdict from `agentdex_engine.evolver.pareto`
- (post-P6) run_expedition_orchestrator from `agentdex_engine.expedition`

Pydantic strict + extra="forbid" enforced on all Cards.
"""

from agentdex_engine.cards import EvolutionCard, ResultCard, Seed, TaskCard

__all__ = ["EvolutionCard", "ResultCard", "Seed", "TaskCard"]
