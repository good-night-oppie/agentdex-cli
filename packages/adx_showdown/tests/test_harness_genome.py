"""A2 — BattleHarness genome (self-play meta-harness Contract 1)."""

from __future__ import annotations

import math

import pytest
from adx_showdown import BattleHarness, ToolPolicy, seed_harness
from adx_showdown.harness import KNOWN_STRATEGIES
from pydantic import ValidationError


def test_seed_harness_is_a_sane_baseline():
    h = seed_harness()
    assert h.harness_id == "H0-seed"
    assert h.move_selection_strategy == "max_damage"
    assert h.move_selection_strategy in KNOWN_STRATEGIES
    assert h.tool_policy.allow_switch is True
    assert "never forfeit" in h.system_prompt.lower()
    assert h.params  # non-empty knob set for bene to perturb


def test_genome_json_round_trips():
    h = seed_harness()
    blob = h.model_dump()  # the dict/JSON form bene mutates
    assert BattleHarness.model_validate(blob) == h
    # and across a JSON string boundary
    assert BattleHarness.model_validate_json(h.model_dump_json()) == h


def test_bene_style_mutation_revalidates():
    """bene perturbs system_prompt + params + move_selection_strategy."""
    g = seed_harness().model_dump()
    g["system_prompt"] = g["system_prompt"] + " Prefer setup when safe."
    g["move_selection_strategy"] = "heuristic"
    g["params"]["aggression"] = 0.7
    g["params"]["new_knob"] = 3  # bene may introduce knobs
    mutant = BattleHarness.model_validate(g)
    assert mutant.move_selection_strategy == "heuristic"
    assert mutant.params["aggression"] == 0.7
    assert mutant.params["new_knob"] == 3


def test_extra_keys_rejected():
    g = seed_harness().model_dump()
    g["smuggled"] = "nope"
    with pytest.raises(ValidationError):
        BattleHarness.model_validate(g)


def test_required_harness_id_nonempty():
    with pytest.raises(ValidationError):
        BattleHarness(harness_id="")


def test_known_strategies_cover_bots_plus_llm():
    # bot-backed strategies A1 can resolve + the codex deferral
    for s in ("random", "max_damage", "heuristic", "stall", "trick_room", "llm_freeform"):
        assert s in KNOWN_STRATEGIES


def test_tool_policy_lookahead_nonnegative():
    ToolPolicy(lookahead_depth=0)  # ok
    with pytest.raises(ValidationError):
        ToolPolicy(lookahead_depth=-1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_float_params_rejected(bad):
    """bene may mutate a knob to nan/inf — those break the JSON round-trip, so reject."""
    with pytest.raises(ValidationError):
        BattleHarness(harness_id="h", params={"aggression": bad})


def test_finite_float_params_round_trip():
    h = BattleHarness(harness_id="h", params={"aggression": 0.7, "n": 3, "flag": True, "tag": "x"})
    again = BattleHarness.model_validate_json(h.model_dump_json())
    assert again == h
    assert all(math.isfinite(v) for v in again.params.values() if isinstance(v, float))
