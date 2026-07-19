"""Tests for constrained-Pareto objective-ordered selection."""

from __future__ import annotations

import pytest
from adx_frontier.candidate import FRONTIER_AXES
from adx_frontier.ledger import FrontierRecord, TrustReceipt
from adx_frontier.selection import objective_axes, select


def _rec(candidate: str, q: float, c: float, w: float) -> FrontierRecord:
    return FrontierRecord(
        candidate=candidate,
        ladder_id="job:test",
        base_model="adx-pool",
        scores={"quality": q, "cost_dollar": c, "wall_clock_sec": w},
        budget_usd=1.0,
        budget_wall_clock_min=10.0,
        receipt=TrustReceipt(
            tier="self_reported",
            kind="adx-run-fake",
            artifacts=("seeds:test",),
        ),
        measured_at_utc="2026-07-18T00:00:00Z",
    )


def test_objective_axes_empty_yields_frontier_axes_order() -> None:
    assert objective_axes([]) == list(FRONTIER_AXES)


def test_objective_axes_maps_tokens_and_appends_missing() -> None:
    assert objective_axes(["latency", "correctness", "cost"]) == [
        "wall_clock_sec",
        "quality",
        "cost_dollar",
    ]


def test_objective_axes_casefolds_then_maps() -> None:
    assert objective_axes(["Latency", "Cost", "Correctness"]) == [
        "wall_clock_sec",
        "cost_dollar",
        "quality",
    ]


def test_objective_axes_rejects_unknown_token() -> None:
    with pytest.raises(ValueError, match="bogus"):
        objective_axes(["bogus"])


def test_objective_axes_dedupes_case_variants() -> None:
    assert objective_axes(["speed", "latency", "quality"]) == [
        "wall_clock_sec",
        "quality",
        "cost_dollar",
    ]


def test_select_excludes_dominated() -> None:
    survivors = select(
        [_rec("best", 0.9, 0.1, 10.0), _rec("dominated", 0.5, 0.2, 20.0)],
        ["correctness"],
    )
    assert [r.candidate for r in survivors] == ["best"]


def test_select_objective_picks_quality_or_cost_tradeoff() -> None:
    high_q = _rec("high-q", 0.95, 0.40, 30.0)
    cheap = _rec("cheap", 0.70, 0.05, 40.0)
    by_quality = select([high_q, cheap], ["correctness", "cost", "latency"])
    by_cost = select([high_q, cheap], ["cost", "correctness", "latency"])
    assert by_quality[0].candidate == "high-q"
    assert by_cost[0].candidate == "cheap"


def test_select_max_cost_prunes() -> None:
    survivors = select(
        [_rec("ok", 0.8, 0.10, 10.0), _rec("pricey", 0.99, 0.80, 10.0)],
        ["correctness"],
        max_cost_dollar=0.50,
    )
    assert [r.candidate for r in survivors] == ["ok"]


def test_select_pruning_everyone_returns_empty() -> None:
    assert (
        select(
            [_rec("a", 0.9, 0.80, 10.0), _rec("b", 0.8, 0.90, 10.0)],
            ["cost"],
            max_cost_dollar=0.01,
        )
        == []
    )


def test_select_tie_break_on_candidate() -> None:
    a = _rec("aaa", 0.5, 0.1, 10.0)
    b = _rec("zzz", 0.5, 0.1, 10.0)
    assert [r.candidate for r in select([b, a], ["correctness"])] == ["aaa", "zzz"]
