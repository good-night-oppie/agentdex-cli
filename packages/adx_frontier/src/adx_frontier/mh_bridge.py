"""Collaborative AgentCandidate → Bene genome → ACCEPT-only promotion bridge."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from adx_frontier.candidate import FRONTIER_AXES, AgentCandidate


@dataclass(frozen=True)
class BeneApi:
    genome_from_candidate: Callable[[dict[str, Any]], Any]
    auto_promote_evolved: Callable[..., Any]


@dataclass(frozen=True)
class BridgeOutcome:
    candidate_engram_id: str
    genome_id: str
    promoted: bool
    status: str
    verdict_engram: str | None
    reason: str


def _load_bene_api() -> BeneApi:
    from bene.kernel.adapters import genome_from_candidate
    from bene.kernel.evolve import auto_promote_evolved

    return BeneApi(genome_from_candidate, auto_promote_evolved)


def bridge_collaborative_candidate(
    candidate: AgentCandidate,
    *,
    ladder_id: str,
    scores: Mapping[str, float],
    baseline: Mapping[str, float],
    metric: str,
    store: Any,
    conn: Any,
    agent_id: str,
    delta: float = 0.0,
    api: BeneApi | None = None,
) -> BridgeOutcome:
    """Persist a tier-4 genome and delegate promotion to Bene's kill gate.

    ``agent_id`` must be an ID registered in the target Bene database.
    """
    candidate.validate()
    subject = _validated_axes(scores, "scores")
    reference = _validated_axes(baseline, "baseline")
    if metric not in subject or metric not in reference:
        raise ValueError(f"promotion metric {metric!r} must exist in scores and baseline")
    backend = api or _load_bene_api()
    genome = backend.genome_from_candidate(
        {
            "name": candidate.name,
            "entrypoint": candidate.entrypoint,
            "strategy": candidate.entrypoint,
            "base_model": candidate.base_model,
            "ladders": list(candidate.ladders),
            "budget": {
                "usd": candidate.budget.usd,
                "wall_clock_min": candidate.budget.wall_clock_min,
            },
            "scores": subject,
        }
    )
    genome.scores = subject
    metadata = {
        "source": "agentdex.collaborative",
        "candidate": candidate.name,
        "genome_id": genome.genome_id,
        "ladder_id": ladder_id,
        "base_model": candidate.base_model,
        "scores": subject,
        "promotion_requires": "ACCEPT verdict linked via verifies",
    }
    engram_id = store.append(
        "strategic",
        f"mh-candidate:{candidate.name}",
        genome.encode(),
        tier=4,
        provenance={"agent_id": agent_id},
        agent_id=agent_id,
        metadata=metadata,
    )
    genome.engram_id = engram_id
    outcome = backend.auto_promote_evolved(
        engram_id,
        metric=metric,
        subject=subject,
        baseline=reference,
        store=store,
        conn=conn,
        delta=delta,
        probe_name=f"agentdex:{ladder_id}:{candidate.name}",
    )
    return BridgeOutcome(
        candidate_engram_id=engram_id,
        genome_id=genome.genome_id,
        promoted=bool(outcome.promoted),
        status=str(outcome.status),
        verdict_engram=outcome.verdict_engram,
        reason=str(outcome.reason),
    )


def _validated_axes(values: Mapping[str, float], label: str) -> dict[str, float]:
    missing = [axis for axis in FRONTIER_AXES if axis not in values]
    if missing:
        raise ValueError(f"{label} missing frontier axes: {missing}")
    result = {axis: float(values[axis]) for axis in FRONTIER_AXES}
    if any(not math.isfinite(value) for value in result.values()):
        raise ValueError(f"{label} frontier axes must be finite")
    return result
