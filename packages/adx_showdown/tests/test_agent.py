"""The Agent abstraction — the generic decision seam different backends inherit.

Generalizes the codex-specific framing: ``Agent`` is the ABC, ``CodexAgent`` is the
codex backend (delegates verbatim to ``codex_decide``), ``GreedyAgent`` is the
zero-cost deterministic default. An ``Agent`` instance is itself a ``DecideFn``, so
it is a drop-in for ``select_codex_move(decide=...)``.
"""

from __future__ import annotations

import pytest
from adx_showdown.selfplay.agent import Agent, CodexAgent, GreedyAgent, agent_decide


def test_agent_is_abstract():
    with pytest.raises(TypeError):
        Agent()  # the ABC itself cannot be instantiated

    class NoDecide(Agent):
        pass

    with pytest.raises(TypeError):
        NoDecide()  # a subclass that doesn't implement decide() is still abstract


def test_custom_agent_is_a_drop_in_decidefn():
    class FixedAgent(Agent):
        name = "fixed"

        def decide(self, harness, ctx):
            return (ctx.get("available_moves") or [{}])[0].get("id")

    a = FixedAgent()
    assert isinstance(a, Agent)
    # callable with the DecideFn shape (harness, ctx) -> action id
    assert a(None, {"available_moves": [{"id": "tackle"}]}) == "tackle"
    assert a(None, {"available_moves": []}) is None  # abstain shape
    # agent_decide is the backend-agnostic entry point (identity-with-typing)
    assert agent_decide(a) is a


def test_codex_agent_delegates_to_codex_decide_without_shelling_out():
    seen: dict[str, str] = {}

    def fake_run(prompt, schema, timeout):
        seen["prompt"] = prompt
        return {"move_id": "thunderbolt"}

    agent = CodexAgent(run=fake_run)
    assert agent.name == "codex"
    out = agent(None, {"available_moves": [{"id": "thunderbolt", "type": "Electric"}]})
    assert out == "thunderbolt"
    assert "thunderbolt" in seen["prompt"]  # the legal id reached codex's prompt


def test_greedy_agent_picks_max_power_and_abstains_cleanly():
    g = GreedyAgent()
    assert isinstance(g, Agent) and g.name == "greedy"
    ctx = {
        "available_moves": [
            {"id": "ember", "base_power": 40},
            {"id": "flamethrower", "base_power": 90},
        ]
    }
    assert g(None, ctx) == "flamethrower"
    assert g(None, {}) is None  # no legal action -> abstain, no subprocess, never raises


def test_runner_resolves_an_agent_under_live_flag(monkeypatch):
    from adx_showdown.selfplay import runner

    monkeypatch.delenv("ADX_CODEX_LIVE", raising=False)
    assert runner._resolve_agent() is None  # default -> greedy (None decide)

    monkeypatch.setenv("ADX_CODEX_LIVE", "1")
    a = runner._resolve_agent()
    assert isinstance(a, CodexAgent)
    assert runner._resolve_codex_decide is runner._resolve_agent  # back-compat alias
