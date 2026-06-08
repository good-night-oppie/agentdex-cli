"""Phase-6 Pareto verdict tests."""
from __future__ import annotations

from agentdex_engine.cards import ResultCard
from agentdex_engine.evolver.pareto import ParetoVerdict, pareto_verdict


def _rc(agent_id: str, pass_rate: float, cost: float, speed: float) -> ResultCard:
    return ResultCard(
        expedition_id="test-expedition",
        task_id="test-task",
        agent_id=agent_id,
        pass_rate=pass_rate,
        cost_dollar=cost,
        cost_token=0,
        speed_wall_clock_sec=speed,
        failure_trace_path=None,
        pareto_position="undominated",
        langfuse_trace_id=None,
        langfuse_trace_url=None,
    )


def test_clear_winner():
    """One card strictly Pareto-dominates both others → winner identified."""
    cards = [
        _rc("alpha", pass_rate=0.95, cost=0.10, speed=2.0),
        _rc("beta", pass_rate=0.80, cost=0.50, speed=4.0),
        _rc("gamma", pass_rate=0.70, cost=1.00, speed=6.0),
    ]
    verdict = pareto_verdict(cards)
    assert isinstance(verdict, ParetoVerdict)
    assert verdict.verdict_kind == "undominated"
    assert verdict.winner == "alpha"
    assert verdict.rankings["alpha"]["pass_rate"] == 1


def test_no_clear_winner_when_none_dominates():
    """Each card excels at a different objective → no clear winner."""
    cards = [
        _rc("fast", pass_rate=0.70, cost=0.30, speed=1.0),     # fastest
        _rc("cheap", pass_rate=0.70, cost=0.05, speed=5.0),    # cheapest
        _rc("accurate", pass_rate=0.95, cost=0.50, speed=5.0),  # most accurate
    ]
    verdict = pareto_verdict(cards)
    assert verdict.verdict_kind == "no_clear_winner"
    assert verdict.winner is None


def test_tied_pair_no_clear_winner():
    """Two cards perfectly tied → no_clear_winner."""
    cards = [
        _rc("twin_a", pass_rate=0.80, cost=0.20, speed=3.0),
        _rc("twin_b", pass_rate=0.80, cost=0.20, speed=3.0),
    ]
    verdict = pareto_verdict(cards)
    assert verdict.verdict_kind == "no_clear_winner"


def test_single_card_is_winner_by_default():
    cards = [_rc("solo", pass_rate=0.50, cost=0.99, speed=99.0)]
    verdict = pareto_verdict(cards)
    assert verdict.verdict_kind == "undominated"
    assert verdict.winner == "solo"


def test_empty_input_no_clear_winner():
    verdict = pareto_verdict([])
    assert verdict.verdict_kind == "no_clear_winner"
    assert verdict.winner is None


def test_rankings_have_all_three_metrics():
    cards = [
        _rc("alpha", pass_rate=0.95, cost=0.10, speed=2.0),
        _rc("beta", pass_rate=0.80, cost=0.50, speed=4.0),
    ]
    verdict = pareto_verdict(cards)
    for ranks in verdict.rankings.values():
        assert set(ranks.keys()) == {"pass_rate", "cost_dollar", "speed_wall_clock_sec"}
