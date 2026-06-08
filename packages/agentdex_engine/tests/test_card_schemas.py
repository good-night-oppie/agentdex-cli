"""Three Cards schema tests — ≥9 (3 fixtures × 3 Cards minimum)."""

import pytest
from pydantic import ValidationError

from agentdex_engine.cards import TaskCard, ResultCard, EvolutionCard
from card_fixtures import (
    task_card_examples as tcf,
    result_card_examples as rcf,
    evolution_card_examples as ecf,
)


# ─── TaskCard ────────────────────────────────────────────────────────────────


def test_task_card_positive():
    tc = TaskCard.model_validate(tcf.POSITIVE)
    assert tc.id == "nvidia-earnings-infographic-q3-fy2026"
    assert tc.budget_token_cap == 200000
    assert tc.expected_output_kind == "infographic"


def test_task_card_negative_extra_field_forbidden():
    with pytest.raises(ValidationError) as exc:
        TaskCard.model_validate(tcf.NEGATIVE_EXTRA_FIELD)
    assert "extra" in str(exc.value).lower() or "rogue_field" in str(exc.value)


def test_task_card_boundary_zero_budgets():
    tc = TaskCard.model_validate(tcf.BOUNDARY_MIN_BUDGET)
    assert tc.budget_token_cap == 0
    assert tc.budget_dollar_cap == 0.0


# ─── ResultCard ──────────────────────────────────────────────────────────────


def test_result_card_positive():
    rc = ResultCard.model_validate(rcf.POSITIVE)
    assert rc.agent_id == "claude"
    assert rc.pass_rate == 0.85
    assert rc.langfuse_trace_url is not None


def test_result_card_negative_pass_rate_out_of_range():
    with pytest.raises(ValidationError) as exc:
        ResultCard.model_validate(rcf.NEGATIVE_OUT_OF_RANGE_PASS_RATE)
    assert "pass_rate" in str(exc.value)


def test_result_card_boundary_zero_and_dominated():
    rc = ResultCard.model_validate(rcf.BOUNDARY_ZERO_PASS_RATE)
    assert rc.pass_rate == 0.0
    assert rc.pareto_position == "dominated"
    assert rc.failure_trace_path is not None


# ─── EvolutionCard ───────────────────────────────────────────────────────────


def test_evolution_card_positive():
    ec = EvolutionCard.model_validate(ecf.POSITIVE)
    assert ec.expedition_id == "nvidia-q3-fy2026-exp-001"
    assert "source" in ec.mutation_seeds
    assert ec.mutation_seeds["source"][0].seed_provenance == "structural"
    assert len(ec.langfuse_trace_urls) == 3


def test_evolution_card_negative_bad_category_key():
    with pytest.raises(ValidationError) as exc:
        EvolutionCard.model_validate(ecf.NEGATIVE_BAD_CATEGORY_KEY)
    assert "wrong_category" in str(exc.value) or "literal" in str(exc.value).lower()


def test_evolution_card_boundary_empty_all_categories():
    ec = EvolutionCard.model_validate(ecf.BOUNDARY_EMPTY_SEEDS_ALL_CATEGORIES)
    assert all(len(v) == 0 for v in ec.mutation_seeds.values())
    assert set(ec.mutation_seeds.keys()) == {"source", "reasoning", "coding", "control", "harness"}
