"""M7 learned-seed Protocol scaffold (closes DEFERRED M7-scaffold partially —
real learning implementation is post-MVP, Phase-9+).

What "learned" means in agentdex-cli (per ADR-0009 §D5 + R6 truth-in-
advertising amendment):

- ``structural`` seeds are emitted MECHANICALLY by the Oracle layer
  (provenance-gap → source seed; soft-judge uncertainty → harness seed;
  response-shape variance → control seed; M5 floor → reasoning seed).
  These fire on every Expedition regardless of whether the system
  actually "learned" anything; the M5 gate only requires them to be
  PRESENT with honest provenance labeling.

- ``learned`` seeds are emitted by analyzing CROSS-EXPEDITION lineage:
  patterns that recur in the KAOS lineage entries across N expeditions,
  trends in mutation-seed kinds that correlate with verdict shifts,
  emergent strategies that one baseline discovers and others adopt over
  time. M7 raises the EvolutionCard quality bar to require ≥1 learned
  seed per Expedition so the Pokédex actually accumulates learning, not
  just structural log entries.

This file ships the PROTOCOL + a deterministic placeholder generator
that flags multi-Expedition recurrence patterns as learned seeds — NOT
ML. Real ML lands when the substrate has the data to learn from
(post-M9 helios hot tier + KAOS dream consolidation pipeline).

Anchor:
- ADR-0009 §D5 M5 gate vs M7 gate distinction
- IDEAL_EXPERIENCE.md Failure mode #4 "Tautological MVP gate"
- DEFERRED.md M7-scaffold row (created by this PR)
- repair.py OracleRepairFlagger (structural counterpart)
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Protocol

import yaml

from agentdex_engine.cards import EvolutionCard, Seed, SeedCategory


class LearnedSeedGenerator(Protocol):
    """Generates ``seed_provenance="learned"`` seeds from cross-Expedition
    lineage.

    Implementations choose how to read lineage (KAOS query, raw YAML walk,
    helios stream) + how to summarise. The Protocol is intentionally
    narrow so the M7 gate can swap in a real ML implementation later
    without breaking the orchestrator wiring.
    """

    def emit_seeds(self, current_expedition_id: str) -> dict[SeedCategory, list[Seed]]:
        """Return a mutation_seeds dict suitable for merging into
        :class:`EvolutionCard.mutation_seeds`. Empty dict if no learned
        signal has accumulated yet (acceptable at M5-M6; M7 raises bar).
        """
        ...


class RecurrencePatternGenerator:
    """Placeholder learned-seed generator (no ML — pure cross-expedition
    pattern counting).

    Walks recent ``expeditions/<id>/evolution_card.yaml`` files, counts
    seed.kind frequency, and emits a ``reasoning`` seed when one kind
    recurs ≥``threshold`` times. Recurrence is a weak proxy for "the
    system noticed something stable" — better than the mechanical M5
    floor seed but weaker than real ML. Honest provenance label.

    Designed to be swapped out by ``MlLearnedSeedGenerator`` (post-helios)
    without touching the Expedition orchestrator call site.
    """

    def __init__(
        self,
        expeditions_root,
        *,
        window: int = 5,
        recurrence_threshold: int = 3,
        skip_expedition_ids: Iterable[str] = (),
    ):
        self.expeditions_root = expeditions_root
        self.window = window
        self.recurrence_threshold = recurrence_threshold
        self._skip = set(skip_expedition_ids)

    def emit_seeds(self, current_expedition_id: str) -> dict[SeedCategory, list[Seed]]:
        from pathlib import Path

        root = Path(self.expeditions_root)
        if not root.is_dir():
            return {}

        # Exclude the current expedition + any explicit skip list (e.g.
        # smoke-test artifacts that would dominate the window).
        skip = self._skip | {current_expedition_id}

        # Most-recent <window> expeditions w/ evolution_card.yaml.
        dirs = sorted(
            (
                d
                for d in root.iterdir()
                if d.is_dir() and d.name not in skip and (d / "evolution_card.yaml").is_file()
            ),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )[: self.window]

        kind_freq: Counter[tuple[str, str]] = Counter()
        for d in dirs:
            try:
                evo = yaml.safe_load((d / "evolution_card.yaml").read_text())
            except (yaml.YAMLError, OSError):
                continue
            seeds = (evo or {}).get("mutation_seeds") or {}
            for cat, items in seeds.items():
                for s in items or []:
                    if isinstance(s, dict) and s.get("kind"):
                        kind_freq[(cat, s["kind"])] += 1

        out: dict[SeedCategory, list[Seed]] = {}
        for (cat, kind), n in kind_freq.most_common():
            if n < self.recurrence_threshold:
                break
            seed = Seed(
                kind=f"recurrence/{kind}",
                description=(
                    f"Cross-expedition pattern: seed.kind={kind!r} fired "
                    f"{n}× in the last {len(dirs)} expeditions. The system "
                    "has accumulated enough evidence that this is a stable "
                    "signal worth a Pokédex entry, not single-run noise."
                ),
                evidence_jsonl_excerpt=(
                    f'{{"window":{len(dirs)},"recurrence":{n},"category":{cat!r},"kind":{kind!r}}}'
                ),
                confidence="med",
                seed_provenance="learned",
            )
            # Promote learned seeds into a `reasoning` bucket — they reflect
            # accumulated cross-run inference, not a structural one-shot.
            out.setdefault("reasoning", []).append(seed)
        return out


def merge_learned_into_evolution_card(
    card: EvolutionCard, learned: dict[SeedCategory, list[Seed]]
) -> EvolutionCard:
    """Return a copy of ``card`` with ``learned`` seeds merged into
    ``mutation_seeds``. Pydantic strict-validate via ``model_validate``.

    M7 gate consumers check
    ``any(s.seed_provenance == "learned" for cat in card.mutation_seeds for s
    in card.mutation_seeds[cat])``.
    """
    merged: dict[SeedCategory, list[Seed]] = {
        cat: list(seeds) for cat, seeds in (card.mutation_seeds or {}).items()
    }
    for cat, seeds in (learned or {}).items():
        merged.setdefault(cat, []).extend(seeds)
    payload = card.model_dump()
    payload["mutation_seeds"] = {
        cat: [s.model_dump() if hasattr(s, "model_dump") else s for s in seeds]
        for cat, seeds in merged.items()
    }
    return EvolutionCard.model_validate(payload)


__all__ = [
    "LearnedSeedGenerator",
    "RecurrencePatternGenerator",
    "merge_learned_into_evolution_card",
]
