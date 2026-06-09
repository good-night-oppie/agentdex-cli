"""M7 learned-seed Protocol + RecurrencePatternGenerator tests.

Closes DEFERRED M7-scaffold partially — the Protocol surface + the
recurrence-pattern placeholder + the merge helper are wired with full
test coverage. The real ML generator is post-M9 (helios hot tier).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentdex_engine.cards import EvolutionCard, Seed
from agentdex_engine.evolver.learned_seeds import (
    LearnedSeedGenerator,
    RecurrencePatternGenerator,
    merge_learned_into_evolution_card,
)


def _write_expedition(tmp_path: Path, exp_id: str, seeds_by_cat: dict) -> Path:
    d = tmp_path / exp_id
    d.mkdir()
    card_payload = {
        "expedition_id": exp_id,
        "parent_lineage_root": None,
        "winning_pattern": "stub",
        "losing_pattern": "stub",
        "mutation_seeds": {
            cat: [
                {
                    "kind": kind,
                    "description": "stub",
                    "evidence_jsonl_excerpt": "{}",
                    "confidence": "med",
                    "seed_provenance": "structural",
                }
                for kind in kinds
            ]
            for cat, kinds in seeds_by_cat.items()
        },
        "boundary_annotations": [],
        "langfuse_trace_urls": {},
    }
    (d / "evolution_card.yaml").write_text(yaml.safe_dump(card_payload))
    return d


def test_protocol_satisfied_by_recurrence_generator():
    """RecurrencePatternGenerator structurally satisfies the Protocol."""
    gen: LearnedSeedGenerator = RecurrencePatternGenerator(expeditions_root="/tmp")
    # Static type check via runtime instance check — Protocol is @runtime_checkable
    # only if decorated; this verifies the duck-typed signature instead.
    assert hasattr(gen, "emit_seeds")
    assert callable(gen.emit_seeds)


def test_no_expeditions_yields_empty(tmp_path: Path):
    """Empty expeditions root → no learned seeds; gate stays open."""
    gen = RecurrencePatternGenerator(expeditions_root=tmp_path)
    assert gen.emit_seeds("current-exp") == {}


def test_recurrence_below_threshold_emits_nothing(tmp_path: Path):
    """Pattern firing ≤2× across the window is below the default threshold of 3.

    Each fixture expedition uses a unique seed.kind so no single kind
    exceeds the threshold (we want to test the threshold gate, not
    accidentally trip it on a different kind).
    """
    for i in range(5):
        _write_expedition(tmp_path, f"exp-{i}", {"source": [f"unique_kind_{i}"]})
    gen = RecurrencePatternGenerator(
        expeditions_root=tmp_path, window=5, recurrence_threshold=3
    )
    assert gen.emit_seeds("current-exp") == {}


def test_recurrence_above_threshold_emits_learned_reasoning_seed(tmp_path: Path):
    """Same seed.kind firing 3+ times across the window → learned seed."""
    for i in range(5):
        _write_expedition(
            tmp_path,
            f"exp-{i}",
            {"source": ["provenance_required"], "control": ["response_shape_variance"]},
        )
    gen = RecurrencePatternGenerator(
        expeditions_root=tmp_path, window=5, recurrence_threshold=3
    )
    out = gen.emit_seeds("current-exp")
    assert "reasoning" in out, f"expected reasoning category, got {list(out)}"
    seeds = out["reasoning"]
    assert len(seeds) == 2, f"expected 2 recurring kinds, got {len(seeds)}"
    assert all(isinstance(s, Seed) for s in seeds)
    assert all(s.seed_provenance == "learned" for s in seeds), (
        "every recurrence seed MUST carry seed_provenance='learned' per R6"
    )
    kinds = {s.kind for s in seeds}
    assert kinds == {"recurrence/provenance_required", "recurrence/response_shape_variance"}


def test_current_expedition_excluded_from_window(tmp_path: Path):
    """The expedition being judged must NOT count itself toward recurrence."""
    _write_expedition(tmp_path, "current", {"source": ["should_not_inflate"]})
    for i in range(2):
        _write_expedition(tmp_path, f"prior-{i}", {"source": ["should_not_inflate"]})
    gen = RecurrencePatternGenerator(
        expeditions_root=tmp_path, window=5, recurrence_threshold=3
    )
    # 2 prior + 1 current; current is excluded → 2 hits, below threshold
    assert gen.emit_seeds("current") == {}


def test_merge_learned_into_evolution_card_preserves_structural():
    """The merge helper combines structural + learned without overwriting."""
    base = EvolutionCard(
        expedition_id="exp-test",
        parent_lineage_root=None,
        winning_pattern="stub",
        losing_pattern="stub",
        mutation_seeds={
            "source": [
                Seed(
                    kind="provenance_required",
                    description="stub",
                    evidence_jsonl_excerpt="{}",
                    confidence="high",
                    seed_provenance="structural",
                )
            ]
        },
        boundary_annotations=[],
        langfuse_trace_urls={},
    )
    learned = {
        "reasoning": [
            Seed(
                kind="recurrence/provenance_required",
                description="stub",
                evidence_jsonl_excerpt="{}",
                confidence="med",
                seed_provenance="learned",
            )
        ]
    }
    merged = merge_learned_into_evolution_card(base, learned)
    assert "source" in merged.mutation_seeds  # structural preserved
    assert "reasoning" in merged.mutation_seeds  # learned added
    provs = {
        s.seed_provenance
        for cat in merged.mutation_seeds.values()
        for s in cat
    }
    assert provs == {"structural", "learned"}, (
        f"merge should preserve both provenance labels; got {provs}"
    )


def test_m7_gate_check_pattern():
    """M7 gate snippet: ≥1 learned seed in the EvolutionCard.

    This test documents the gate condition consumers should use; if the
    Literal shape changes, this test breaks first.
    """
    card = EvolutionCard(
        expedition_id="exp-m7",
        parent_lineage_root=None,
        winning_pattern="stub",
        losing_pattern="stub",
        mutation_seeds={
            "source": [
                Seed(
                    kind="provenance_required",
                    description="stub",
                    evidence_jsonl_excerpt="{}",
                    confidence="high",
                    seed_provenance="structural",
                )
            ]
        },
        boundary_annotations=[],
        langfuse_trace_urls={},
    )
    has_learned = any(
        s.seed_provenance == "learned"
        for cat in card.mutation_seeds.values()
        for s in cat
    )
    assert has_learned is False, "M5 card has only structural seeds"

    learned_seed = Seed(
        kind="recurrence/x",
        description="stub",
        evidence_jsonl_excerpt="{}",
        confidence="med",
        seed_provenance="learned",
    )
    card_m7 = merge_learned_into_evolution_card(card, {"reasoning": [learned_seed]})
    has_learned_m7 = any(
        s.seed_provenance == "learned"
        for cat in card_m7.mutation_seeds.values()
        for s in cat
    )
    assert has_learned_m7 is True, "M7-merged card should report ≥1 learned seed"
