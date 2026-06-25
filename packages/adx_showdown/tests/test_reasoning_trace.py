"""ReasoningTrace — the per-battle agent-reasoning document (arena2d data contract)."""

from __future__ import annotations

import pytest
from adx_showdown.reasoning_trace import (
    SCHEMA_VERSION,
    ConsideredMove,
    Decision,
    ReasoningTrace,
)
from pydantic import ValidationError

_CAPTURE = {
    "battle_tag": "battle-gen9randombattle-7",
    "battle_format": "gen9randombattle",
    "result": {"winner": "p2", "turns": 23},
    "log": ["|init|battle", "|turn|1", "|move|p1a: Tyranitar|Stone Edge|p2a: Iron Moth"],
    "turns": [
        {
            "turn": 1,
            "move": "stoneedge",
            "rationale": "4x weak to Rock",
            "active_species": "Tyranitar",
            "opponent_species": "Iron Moth",
            "considered": [
                {"move": "crunch", "why_not": "only neutral"},
                {"move": "icepunch", "why_not": "resisted"},
            ],
        },
        # an abstain/error row — no move; must be dropped, not turned into a decision
        {"turn": 2, "move": "", "rationale": "", "considered": [], "error": "boom"},
        {
            "turn": 3,
            "move": "zamazenta",
            "rationale": "resists Grass",
            "active_species": "Tyranitar",
            "opponent_species": "Decidueye",
            "considered": [],
        },
    ],
}


def test_from_capture_drops_abstain_rows_and_reindexes_seq():
    tr = ReasoningTrace.from_capture(_CAPTURE)
    assert [d.move for d in tr.decisions] == ["stoneedge", "zamazenta"]  # blank row dropped
    assert [d.seq for d in tr.decisions] == [0, 1]  # seq is contiguous, not the turn index
    assert tr.result.winner == "p2"
    assert tr.result.turns == 23
    assert tr.battle_id == "battle-gen9randombattle-7"


def test_from_capture_carries_attested_fan_and_context():
    tr = ReasoningTrace.from_capture(_CAPTURE)
    d0 = tr.decisions[0]
    assert d0.active == "Tyranitar" and d0.opponent == "Iron Moth"
    assert [c.move for c in d0.considered] == ["crunch", "icepunch"]
    assert d0.considered[0].why_not == "only neutral"
    assert tr.decisions[1].considered == []  # a fan-less decision is fine


def test_unknown_winner_normalizes():
    cap = {**_CAPTURE, "result": {"winner": "weird", "turns": 5}}
    assert ReasoningTrace.from_capture(cap).result.winner == "unknown"


def test_schema_version_is_pinned():
    assert ReasoningTrace().schema_version == SCHEMA_VERSION == "reasoning_trace/1"


def test_data_js_projection_is_a_strict_subset():
    tr = ReasoningTrace.from_capture(_CAPTURE)
    proj = tr.to_data_js_projection()
    assert set(proj) == {"LOG", "RATIONALES"}
    assert proj["LOG"] == _CAPTURE["log"]
    # chosen + rationale + considered survive; a fan-less entry omits the key entirely
    assert proj["RATIONALES"][0] == {
        "move": "stoneedge",
        "rationale": "4x weak to Rock",
        "considered": [
            {"move": "crunch", "why_not": "only neutral"},
            {"move": "icepunch", "why_not": "resisted"},
        ],
    }
    assert proj["RATIONALES"][1] == {"move": "zamazenta", "rationale": "resists Grass"}
    assert "considered" not in proj["RATIONALES"][1]


def test_models_are_strict_extra_forbid():
    with pytest.raises(ValidationError):
        Decision(seq=0, move="x", surprise="nope")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ConsideredMove(move="x", surprise="nope")  # type: ignore[call-arg]


def test_decision_requires_a_nonempty_move():
    with pytest.raises(ValidationError):
        Decision(seq=0, move="")


def test_round_trips_through_json():
    tr = ReasoningTrace.from_capture(_CAPTURE)
    again = ReasoningTrace.model_validate_json(tr.model_dump_json())
    assert again == tr
