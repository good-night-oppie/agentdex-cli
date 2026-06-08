"""Repair Oracle — meta-oracle that flags weak rubrics as mutation seeds.

Per ADR-0009 + phase-6 §R6 truth-in-advertising amendment: when a soft
Oracle's uncertainty > 0.5, or when a hard Oracle's provenance check
surfaces gaps, this flagger emits :class:`Seed` instances carrying
``seed_provenance="structural"``. Those become the structural-source half
of the EvolutionCard's mutation seeds at M5; M7 raises the bar by
requiring ≥1 seed with ``seed_provenance="learned"``.

The Seed schema (phase-2) constrains ``mutation_seeds`` to a fixed
``Literal["source","reasoning","coding","control","harness"]`` category
dict. Repair seeds map to ``harness`` (the Oracle itself is harness-level
infrastructure); provenance gaps map to ``source`` (per ADR-0009 §Q5 the
source of the citation is what's missing).
"""
from __future__ import annotations

from agentdex_engine.cards import Seed, SeedCategory
from agentdex_engine.oracle.base import OracleVerdictMap


class OracleRepairFlagger:
    """Scans a merged verdict map + emits structural mutation seeds."""

    SOFT_UNCERTAINTY_THRESHOLD = 0.5

    def emit_seeds(self, verdicts: OracleVerdictMap) -> dict[SeedCategory, list[Seed]]:
        """Return a mutation_seeds dict suitable for EvolutionCard.mutation_seeds.

        Empty categories are OMITTED — EvolutionCard accepts a dict whose keys
        are a subset of the 5 SeedCategory literals.
        """
        seeds_by_category: dict[SeedCategory, list[Seed]] = {}

        # --- soft-judge uncertainty / disagreement → harness repair ---
        for key, verdict in verdicts.items():
            if verdict.kind != "soft":
                continue
            if (verdict.uncertainty or 0.0) > self.SOFT_UNCERTAINTY_THRESHOLD:
                seed = Seed(
                    kind="oracle_repair",
                    description=(
                        f"Soft oracle {key!r} returned high uncertainty "
                        f"(u={verdict.uncertainty:.2f}); strengthen rubric or "
                        f"add hard-Oracle cross-check before next Expedition."
                    ),
                    evidence_jsonl_excerpt=_excerpt(key, verdict),
                    confidence="high",
                    seed_provenance="structural",
                )
                seeds_by_category.setdefault("harness", []).append(seed)

        # --- provenance gap → source seed ---
        prov_keys = [
            k for k in verdicts
            if k.endswith("provenance_required") or "provenance" in k
        ]
        for key in prov_keys:
            verdict = verdicts[key]
            if not verdict.pass_:
                seed = Seed(
                    kind="provenance_required",
                    description=(
                        f"Provenance check {key!r} failed (score={verdict.score:.2f}); "
                        "future Expeditions should require every claim to carry a "
                        "`source: <file>:<line>` annotation."
                    ),
                    evidence_jsonl_excerpt=_excerpt(key, verdict),
                    confidence="high",
                    seed_provenance="structural",
                )
                seeds_by_category.setdefault("source", []).append(seed)

        return seeds_by_category


def _excerpt(key: str, verdict) -> str:
    return f'{{"key":{key!r},"kind":{verdict.kind!r},"score":{verdict.score},"evidence":{verdict.evidence!r}}}'
