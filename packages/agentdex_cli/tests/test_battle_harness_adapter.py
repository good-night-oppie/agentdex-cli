from __future__ import annotations

import pytest
from agentdex_cli.battle_harness_adapter import (
    BattleHarness,
    seed_battle_harness,
    select_codex_move,
)


def test_max_damage_is_deterministic_and_tie_breaks_lowest_choice() -> None:
    harness = seed_battle_harness("max_damage")
    state = {
        "status": "your_move",
        "n_choices": 3,
        "choices": [
            {"choice_index": 1, "choice": "move 1", "name": "Quick Attack", "base_power": 40},
            {"choice_index": 2, "choice": "move 2", "name": "Tackle", "base_power": 50},
            {"choice_index": 3, "choice": "move 3", "name": "Scratch", "base_power": 50},
        ],
    }

    first = select_codex_move(harness, state)
    second = select_codex_move(harness, state)

    assert first == second
    assert first.choice_index == 2
    assert first.choice == "move 2"
    assert first.strategy == "max_damage"


def test_type_aware_prefers_super_effective_over_larger_resisted_move() -> None:
    harness = seed_battle_harness("type_aware")
    state = {
        "status": "your_move",
        "n_choices": 2,
        "own_types": ["water"],
        "opponent_types": ["fire"],
        "choices": [
            {
                "choice_index": 1,
                "choice": "move 1",
                "name": "Hyper Beam",
                "type": "normal",
                "basePower": 150,
            },
            {
                "choice_index": 2,
                "choice": "move 2",
                "name": "Surf",
                "type": "water",
                "basePower": 90,
            },
        ],
    }

    selection = select_codex_move(harness, state)

    assert selection.choice_index == 2
    assert selection.score == 270.0  # 90 base * 2x fire weakness * 1.5 STAB
    assert "type_aware" in selection.rationale


def test_rendered_mcp_state_falls_back_to_first_legal_choice() -> None:
    harness = seed_battle_harness("max_damage")
    state = {
        "status": "your_move",
        "n_choices": 4,
        "state": "\n".join(
            [
                "# Turn 1 — you are p1",
                "## Your options (reply with the NUMBER of your choice)",
                "1. move 1 — Thunderbolt (pp 15/15)",
                "2. move 2 — Growl (pp 40/40)",
                "3. switch 2 — Bulbasaur (100/100)",
                "4. switch 3 — Charmander (100/100)",
            ]
        ),
    }

    selection = select_codex_move(harness, state)

    assert selection.choice_index == 1
    assert selection.choice == "move 1"


def test_force_switch_selects_first_switch_even_when_switches_disabled() -> None:
    harness = BattleHarness(
        harness_id="no-switch",
        move_selection_strategy="type_aware",
        tool_policy={"allow_switch": False},
    )
    state = {
        "status": "your_move",
        "n_choices": 2,
        "choices": [
            {"choice_index": 1, "choice": "switch 2", "kind": "switch", "name": "Gengar"},
            {"choice_index": 2, "choice": "switch 3", "kind": "switch", "name": "Snorlax"},
        ],
    }

    selection = select_codex_move(harness, state)

    assert selection.choice_index == 1
    assert selection.choice == "switch 2"


def test_harness_mapping_round_trip_and_unknown_strategy_seed_rail() -> None:
    harness = BattleHarness.from_mapping(
        {
            "harness_id": "evolved-1",
            "system_prompt": "prefer high confidence attacks",
            "move_selection_strategy": "llm_freeform",
            "tool_policy": {"allow_switch": True},
            "params": {"accuracy_weight": 1.0},
        }
    )
    state = {
        "status": "your_move",
        "n_choices": 2,
        "choices": [
            {
                "choice_index": 1,
                "choice": "move 1",
                "name": "Zap Cannon",
                "base_power": 120,
                "accuracy": 50,
            },
            {
                "choice_index": 2,
                "choice": "move 2",
                "name": "Thunderbolt",
                "base_power": 90,
                "accuracy": 100,
            },
        ],
    }

    selection = select_codex_move(harness.to_dict(), state)

    assert selection.strategy == "max_damage"
    assert selection.choice_index == 2


def test_no_legal_choices_is_explicit_error() -> None:
    with pytest.raises(ValueError, match="no legal choices"):
        select_codex_move(seed_battle_harness(), {"status": "your_move", "n_choices": 0})


def test_non_numeric_and_out_of_bounds_params_coerced_gracefully() -> None:
    harness = BattleHarness(
        harness_id="malformed-params",
        move_selection_strategy="type_aware",
        tool_policy={"allow_switch": True},
        params={
            "switch_penalty": "not-a-float",
            "stab_multiplier": "nan",
            "accuracy_weight": "inf",
        },
    )
    state = {
        "status": "your_move",
        "n_choices": 2,
        "own_types": ["water"],
        "opponent_types": ["fire"],
        "choices": [
            {
                "choice_index": 1,
                "choice": "move 1",
                "name": "Surf",
                "type": "water",
                "basePower": 10,
            },
            {"choice_index": 2, "choice": "switch 2", "kind": "switch", "name": "Bulbasaur"},
        ],
    }
    selection = select_codex_move(harness, state)
    assert selection.choice_index == 1
    assert selection.score == 30.0

    harness2 = BattleHarness(
        harness_id="acc-weight-clamp",
        move_selection_strategy="max_damage",
        params={
            "accuracy_weight": 2.0,
        },
    )
    state2 = {
        "status": "your_move",
        "n_choices": 2,
        "choices": [
            {
                "choice_index": 1,
                "choice": "move 1",
                "name": "Zap Cannon",
                "base_power": 120,
                "accuracy": 50,
            },
            {
                "choice_index": 2,
                "choice": "move 2",
                "name": "Thunderbolt",
                "base_power": 90,
                "accuracy": 100,
            },
        ],
    }
    selection2 = select_codex_move(harness2, state2)
    assert selection2.choice_index == 2
    assert selection2.score == 90.0

    harness3 = BattleHarness(
        harness_id="stab-clamp",
        move_selection_strategy="type_aware",
        params={
            "stab_multiplier": -5.0,
        },
    )
    state3 = {
        "status": "your_move",
        "n_choices": 2,
        "own_types": ["water"],
        "opponent_types": ["fire"],
        "choices": [
            {
                "choice_index": 1,
                "choice": "move 1",
                "name": "Hyper Beam",
                "type": "normal",
                "basePower": 150,
            },
            {
                "choice_index": 2,
                "choice": "move 2",
                "name": "Surf",
                "type": "water",
                "basePower": 90,
            },
        ],
    }
    selection3 = select_codex_move(harness3, state3)
    assert selection3.choice_index == 1
    assert selection3.score == 150.0
