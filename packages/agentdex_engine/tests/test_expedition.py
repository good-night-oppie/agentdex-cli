"""Smoke test for the Expedition orchestrator (mocked bridges)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentdex_engine.cards import TaskCard
from agentdex_engine.evolver.pareto import ParetoVerdict
from agentdex_engine.expedition import run_expedition_orchestrator
from agentdex_engine.oracle.base import OracleVerdict


class _StubBridge:
    """Minimal async bridge w/ ``send`` + ``cfg.name``."""

    def __init__(self, name: str, response_text: str):
        self._response = response_text
        self.cfg = SimpleNamespace(name=name)

    async def send(self, prompt, *, session_id=None, extra=None):
        return self._response, None


class _StubOracle:
    """Returns canned verdicts keyed by bridge response sentinel."""

    def __init__(self, pass_by_keyword: dict[str, bool]):
        self._pass_by_kw = pass_by_keyword

    def evaluate(self, response, task_card):
        hits = sum(1 for kw, v in self._pass_by_kw.items() if v and kw in response)
        total = max(len(self._pass_by_kw), 1)
        verdicts: dict[str, OracleVerdict] = {}
        for kw, expected in self._pass_by_kw.items():
            passed = expected and (kw in response)
            verdicts[f"hard.{kw}"] = OracleVerdict(
                kind="hard",
                **{"pass": passed},
                score=1.0 if passed else 0.0,
                evidence=f"kw={kw} hit={kw in response}",
            )
        return verdicts


def _task_card() -> TaskCard:
    return TaskCard(
        id="nvidia-earnings-infographic-q3-fy2026",
        source_bundle_hash="9edcd1a12c51f1741d90fab7b733a2144f1831bf7d28a7ead3165052c66dc09c",
        environment_spec={"runtime": "test"},
        oracle_spec_ref="dummy.yaml",
        budget_token_cap=1000,
        budget_dollar_cap=1.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )


def test_orchestrator_returns_three_card_chain():
    bridges = [
        _StubBridge("claude", "revenue gross_margin data_center"),
        _StubBridge("codex", "revenue gross_margin"),
        _StubBridge("manus", "revenue"),
    ]
    oracle = _StubOracle({
        "revenue": True,
        "gross_margin": True,
        "data_center": True,
    })

    result_cards, verdict, evolution_card = asyncio.run(
        run_expedition_orchestrator(
            _task_card(), bridges, oracle, judge_llm="claude-haiku-4.5",
            prompt_override="dummy prompt",
        )
    )

    assert len(result_cards) == 3
    assert isinstance(verdict, ParetoVerdict)
    # The "claude" stub passes ALL 3 keywords → highest pass_rate.
    by_id = {rc.agent_id: rc for rc in result_cards}
    assert by_id["claude"].pass_rate == 1.0
    assert by_id["codex"].pass_rate == pytest.approx(2 / 3)
    assert by_id["manus"].pass_rate == pytest.approx(1 / 3)
    # Wall-clock noise on async stubs makes the Pareto winner non-deterministic;
    # assert orchestrator structure instead. pareto_verdict semantics are
    # exercised by test_pareto.py.
    assert evolution_card.expedition_id.startswith("expedition.")
    assert isinstance(evolution_card.mutation_seeds, dict)
    assert verdict.verdict_kind in {"undominated", "no_clear_winner"}


def test_orchestrator_empty_bridges_returns_no_winner():
    result_cards, verdict, evolution_card = asyncio.run(
        run_expedition_orchestrator(
            _task_card(),
            [],
            _StubOracle({"r": True}),
            judge_llm="claude-haiku-4.5",
            prompt_override="dummy",
        )
    )
    assert result_cards == []
    assert verdict.verdict_kind == "no_clear_winner"
    assert evolution_card.mutation_seeds == {} or all(
        v == [] for v in evolution_card.mutation_seeds.values()
    )
