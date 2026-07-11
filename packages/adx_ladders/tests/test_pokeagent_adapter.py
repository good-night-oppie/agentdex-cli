import pytest
from adx_ladders.adapters.pokeagent import PokeAgentResult


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
