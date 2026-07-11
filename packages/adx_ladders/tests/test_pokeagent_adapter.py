import pytest
from adx_frontier.candidate import AgentCandidate, Budget
from adx_ladders.adapters.pokeagent import PokeAgentAdapter, PokeAgentResult
from adx_ladders.base import LadderClass


def _valid(**overrides: object) -> PokeAgentResult:
    values = dict(rating=1512.0, rating_ref="ladder:adx-bot-1:1512", community_opponents=3,
                  total_opponents=5, wall_clock_sec=12.0, cost_dollar=0.0)
    values.update(overrides)
    return PokeAgentResult(**values)


def test_pokeagent_result_accepts_server_rated_window() -> None:
    result = _valid()
    assert (result.rating, result.community_opponents) == (1512.0, 3)


@pytest.mark.parametrize("overrides", [{"rating_ref": " "}, {"rating": float("nan")}, {"cost_dollar": -1.0}, {"community_opponents": 6}, {"total_opponents": -1}])
def test_pokeagent_result_rejects_untrustworthy_window(overrides: dict) -> None:
    with pytest.raises(ValueError):
        _valid(**overrides)


def test_pokeagent_adapter_emits_verified_static_degraded_measurement(tmp_path) -> None:
    (tmp_path / "agent.py").write_text("pass\n")
    candidate = AgentCandidate("agent", "python agent.py", ("agent.py",), "model", Budget(1, 2),
                               ("pokeagent-gen1ou",), tmp_path)
    calls = []
    adapter = PokeAgentAdapter(lambda entry, timeout: calls.append((entry, timeout)) or _valid(),
                               minimum_community_share=0.75)
    result = adapter.measure(candidate)
    assert result.scores == {"quality": 1512.0, "cost_dollar": 0.0, "wall_clock_sec": 12.0}
    assert result.receipt.tier == "verified" and result.receipt.ref.startswith("ladder:")
    assert result.effective_ladder_class is LadderClass.STATIC
    assert calls == [("python agent.py", 120.0)]
