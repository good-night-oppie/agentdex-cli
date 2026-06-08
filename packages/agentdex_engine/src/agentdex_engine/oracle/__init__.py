"""Oracle layer — Hard / Soft / Repair verdicts feeding the Pareto judge.

Per ADR-0009 §Q5: numbers MUST go through hard match, never LLM-judged. Soft
oracle scores narrative coherence via Langfuse-wrapped Anthropic SDK. Repair
oracle scans verdicts + emits ``oracle_repair`` mutation seeds with
``seed_provenance="structural"`` (R6 truth-in-advertising) so the
EvolutionCard surfaces gaps for future Expeditions.
"""

from agentdex_engine.oracle.base import (
    Oracle,
    OracleChain,
    OracleVerdict,
    OracleVerdictMap,
)

__all__ = [
    "Oracle",
    "OracleChain",
    "OracleVerdict",
    "OracleVerdictMap",
]
