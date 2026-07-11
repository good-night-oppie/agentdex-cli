"""Tests for class-differentiated frontier gate policies."""

import pytest
from adx_frontier.gates import pokeagent_gate_class


def test_pokeagent_gate_class_follows_measured_opponent_mix() -> None:
    gate = pokeagent_gate_class
    assert gate(community_opponents=3, total_opponents=4, minimum_community_share=0.75) == "live_adversarial"
    assert gate(community_opponents=2, total_opponents=4, minimum_community_share=0.75) == "static"
    assert gate(community_opponents=0, total_opponents=0, minimum_community_share=0.0) == "static"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"community_opponents": -1, "total_opponents": 1, "minimum_community_share": 0.5},
        {"community_opponents": 2, "total_opponents": 1, "minimum_community_share": 0.5},
        {"community_opponents": 0, "total_opponents": 1, "minimum_community_share": float("nan")},
    ],
)
def test_pokeagent_gate_class_rejects_invalid_window(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        pokeagent_gate_class(**kwargs)
