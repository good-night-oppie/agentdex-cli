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

# A coherent capture: the log EXECUTES two p1 actions — a turn-1 move (Stone Edge) and a
# turn-2 switch (Zamazenta-Crowned) — plus a pre-turn lead switch (not a decision) and an
# abstain row (no move). Decisions align to the executed actions, so the trace has exactly
# two, in log order, with turn read from the log.
_CAPTURE = {
    "battle_tag": "battle-gen9randombattle-7",
    "battle_format": "gen9randombattle",
    "result": {"winner": "p2", "turns": 23},
    "log": [
        "|player|p1|adxAgent|265|",
        "|player|p2|MaxBasePower|265|",
        "|tier|[Gen 9] Random Battle",
        "|start",
        "|switch|p1a: Tyranitar|Tyranitar, L79, F|288/288",  # LEAD (pre-turn) — not a decision
        "|switch|p2a: Iron Moth|Iron Moth, L78|100/100",
        "|turn|1",
        "|move|p1a: Tyranitar|Stone Edge|p2a: Iron Moth",  # decision 1 @ turn 1
        "|turn|2",
        "|switch|p1a: Zamazenta|Zamazenta-Crowned, L68|238/238",  # decision 2 @ turn 2 (switch)
        "|turn|3",
    ],
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
        # an abstain/error row — no move; must be skipped, not turned into a decision
        {"turn": 0, "move": "", "rationale": "", "considered": [], "error": "boom"},
        {
            "turn": 0,  # capture doesn't carry a real turn; the trace reads it from the log
            "move": "zamazentacrowned",
            "rationale": "resists Grass",
            "active_species": "Tyranitar",
            "opponent_species": "Decidueye",
            "considered": [],
        },
    ],
}


def test_from_capture_aligns_to_executed_actions_and_reindexes_seq():
    tr = ReasoningTrace.from_capture(_CAPTURE)
    assert [d.move for d in tr.decisions] == ["stoneedge", "zamazentacrowned"]
    assert [d.seq for d in tr.decisions] == [0, 1]  # contiguous, not the turn index
    assert tr.result.winner == "p2"
    assert tr.result.turns == 23
    assert tr.battle_id == "battle-gen9randombattle-7"


def test_from_capture_reads_turn_from_the_log_not_the_capture():
    # the capture rows carry turn=0; the trace turn is the enclosing |turn|N in the log
    tr = ReasoningTrace.from_capture(_CAPTURE)
    assert [d.turn for d in tr.decisions] == [1, 2]


def test_from_capture_drops_a_captured_choice_that_never_executed():
    """A capture row whose chosen move has no matching p1 action in the log (a retry /
    a choice computed for a turn that never resolved) must NOT become a phantom decision
    in the immutable trace (review #3473480421)."""
    cap = {
        **_CAPTURE,
        "turns": [
            *_CAPTURE["turns"],
            {
                "turn": 0,
                "move": "earthquake",
                "rationale": "after the battle ended",
                "considered": [],
            },
        ],
    }
    tr = ReasoningTrace.from_capture(cap)
    assert [d.move for d in tr.decisions] == ["stoneedge", "zamazentacrowned"]  # no phantom


def test_from_capture_drops_the_pre_turn_lead_switch():
    # the lead switch is logged before |turn|1 — it is not an agent decision, so even a
    # capture row naming it must not produce a decision.
    cap = {
        **_CAPTURE,
        "turns": [
            {"turn": 0, "move": "tyranitar", "rationale": "lead", "considered": []},
            *_CAPTURE["turns"],
        ],
    }
    tr = ReasoningTrace.from_capture(cap)
    assert [d.move for d in tr.decisions] == ["stoneedge", "zamazentacrowned"]


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
    assert proj["RATIONALES"][1] == {"move": "zamazentacrowned", "rationale": "resists Grass"}
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


def test_ps_replay_projection_mirrors_showdown_shape():
    rep = ReasoningTrace.from_capture(_CAPTURE).to_ps_replay(uploadtime=1700000000)
    # PS base fields a stock replay consumer reads unchanged:
    assert rep["id"] == "battle-gen9randombattle-7"
    assert rep["format"] == "[Gen 9] Random Battle"  # display, from |tier|
    assert rep["formatid"] == "gen9randombattle"  # id
    assert rep["players"] == ["adxAgent", "MaxBasePower"]
    assert rep["uploadtime"] == 1700000000
    assert isinstance(rep["log"], str)  # PS log is ONE newline-joined string, not a list
    assert rep["log"].startswith("|player|p1|adxAgent|265|\n")
    # agentdex extension (additive — PS readers ignore):
    assert rep["schema"] == "reasoning_trace/1"
    assert [d["move"] for d in rep["decisions"]] == ["stoneedge", "zamazentacrowned"]
    assert rep["decisions"][0]["considered"][0]["move"] == "crunch"


def test_ps_replay_players_fallback_when_log_lacks_player_lines():
    cap = {
        "battle_tag": "b",
        "battle_format": "gen9randombattle",
        "result": {"winner": "p2", "turns": 1},
        "log": ["|turn|1", "|move|p1a: Tyranitar|Stone Edge|p2a: Iron Moth"],
        "turns": [{"move": "stoneedge", "rationale": "x", "considered": []}],
    }
    rep = ReasoningTrace.from_capture(cap).to_ps_replay()
    assert rep["players"] == ["p1", "p2"]  # no |player| lines → fallback
    assert rep["format"] == "gen9randombattle"  # no |tier| → falls back to formatid
    assert rep["uploadtime"] is None
