"""Contract-1 genome seam (SPEC Contract 1 / ADR-0014).

The validated pydantic ``BattleHarness`` is the **canonical** Contract-1 type;
bene mutates a plain-dataclass mirror (``bene.kernel.battle.genome.BattleHarness``);
the JSON dict is the wire between the two decoupled repos. These tests pin bene's
dict shape so a cross-repo drift fails HERE (at the seam), not inside a battle.
"""

from __future__ import annotations

import json

import pytest
from adx_showdown.harness import BattleHarness, from_bene_genome, to_bene_genome
from pydantic import ValidationError

# bene.kernel.battle.genome.BattleHarness.to_dict() shape for its seed_harness(),
# pinned here so a bene-side rename / added field is caught by THIS test.
_BENE_GENOME_DICT = {
    "harness_id": "seed-h0",
    "system_prompt": "You are a competitive Pokémon battle agent.",
    "move_selection_strategy": "max_damage",
    "tool_policy": {"allow_switch": True, "lookahead_depth": 1},
    "params": {"aggression": 0.5, "switch_threshold": 0.3, "stall_penalty": 0.1},
}


def test_bene_dict_round_trips_through_canonical_genome():
    h = from_bene_genome(_BENE_GENOME_DICT)
    assert isinstance(h, BattleHarness)
    back = to_bene_genome(h)
    # field fidelity both directions (tool_policy flattens to a plain dict)
    assert back["harness_id"] == _BENE_GENOME_DICT["harness_id"]
    assert back["system_prompt"] == _BENE_GENOME_DICT["system_prompt"]
    assert back["move_selection_strategy"] == _BENE_GENOME_DICT["move_selection_strategy"]
    assert back["tool_policy"] == _BENE_GENOME_DICT["tool_policy"]
    assert back["params"] == _BENE_GENOME_DICT["params"]


def test_from_bene_genome_passes_canonical_through_unchanged():
    h = from_bene_genome(_BENE_GENOME_DICT)
    assert from_bene_genome(h) is h  # already-canonical → identity, no re-validate


def test_canonical_validation_is_the_contract():
    # The drift cases the canonical type rejects AT THE SEAM (not inside a battle):
    with pytest.raises(ValidationError):
        from_bene_genome({**_BENE_GENOME_DICT, "harness_id": ""})  # empty id
    with pytest.raises(ValidationError):
        from_bene_genome({**_BENE_GENOME_DICT, "params": {"x": float("inf")}})  # non-finite
    with pytest.raises(ValidationError):
        from_bene_genome({**_BENE_GENOME_DICT, "bogus_field": 1})  # extra=forbid
    with pytest.raises(ValidationError):
        from_bene_genome(
            {
                **_BENE_GENOME_DICT,
                "tool_policy": {"allow_switch": True, "lookahead_depth": 1, "x": 1},
            }
        )  # ToolPolicy extra=forbid


def test_to_bene_genome_is_a_json_wire_dict():
    # to_bene_genome output must be a plain JSON dict bene.from_dict can rebuild —
    # no pydantic objects leak through (tool_policy is a dict, the whole thing
    # JSON-serializable).
    out = to_bene_genome(from_bene_genome(_BENE_GENOME_DICT))
    assert isinstance(out["tool_policy"], dict)
    assert isinstance(out["params"], dict)
    json.dumps(out)  # raises if a non-JSON value leaked through the seam
