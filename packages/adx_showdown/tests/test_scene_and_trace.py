"""UI-5 + UI-6: scene snapshot + reasoning trace helpers (lineproto).

Pure unit tests — no gateway, no sidecar.
"""

from __future__ import annotations

from adx_showdown.lineproto import (
    extract_trace_lines,
    fold_scene,
    project_frame,
    scene_initial,
)

# ── scene_initial ─────────────────────────────────────────────────────────────


def test_scene_initial_has_both_sides():
    s = scene_initial()
    assert "p1" in s and "p2" in s
    assert s["p1"]["hpFrac"] == 1.0
    assert s["p2"]["hpFrac"] == 1.0
    assert s["weather"] == ""


# ── _parse_hpstatus (via fold_scene) ──────────────────────────────────────────


def test_fold_scene_damage_updates_hpfrac():
    s = scene_initial()
    fold_scene(["|-damage|p1a: Garchomp|60/100"], s)
    assert abs(s["p1"]["hpFrac"] - 0.6) < 1e-6


def test_fold_scene_fnt_sets_zero():
    s = scene_initial()
    fold_scene(["|-damage|p2a: Rotom|0 fnt"], s)
    assert s["p2"]["hpFrac"] == 0.0
    assert s["p2"]["status"] == "fnt"


def test_fold_scene_faint_sets_zero_and_status():
    s = scene_initial()
    fold_scene(["|faint|p2a: Rotom"], s)
    assert s["p2"]["hpFrac"] == 0.0
    assert s["p2"]["status"] == "fnt"


def test_fold_scene_status_and_cure():
    s = scene_initial()
    fold_scene(["|-status|p1a: Pikachu|par"], s)
    assert s["p1"]["status"] == "par"
    fold_scene(["|-curestatus|p1a: Pikachu|par"], s)
    assert s["p1"]["status"] == ""


def test_fold_scene_player_sets_name():
    s = scene_initial()
    fold_scene(["|player|p1|Alice||1500"], s)
    assert s["p1"]["name"] == "Alice"


def test_fold_scene_switch_sets_name_and_hp():
    s = scene_initial()
    fold_scene(["|switch|p1a: Garchomp|Garchomp, L50|176/298"], s)
    assert s["p1"]["name"] == "Garchomp"
    assert abs(s["p1"]["hpFrac"] - 176 / 298) < 1e-6


def test_fold_scene_weather():
    s = scene_initial()
    fold_scene(["|-weather|Sandstorm"], s)
    assert s["weather"] == "Sandstorm"


def test_fold_scene_weather_none_clears():
    s = scene_initial()
    s["weather"] = "Rain"
    fold_scene(["|-weather|none"], s)
    assert s["weather"] == ""


def test_fold_scene_accumulates_across_calls():
    s = scene_initial()
    fold_scene(["|player|p1|Alice||", "|player|p2|Bob||"], s)
    fold_scene(["|-damage|p1a: Garchomp|120/298"], s)
    fold_scene(["|-damage|p2a: Rotom|35/100"], s)
    assert s["p1"]["name"] == "Alice"
    assert s["p2"]["name"] == "Bob"
    assert abs(s["p1"]["hpFrac"] - 120 / 298) < 1e-6
    assert abs(s["p2"]["hpFrac"] - 0.35) < 1e-6


def test_fold_scene_ignores_timestamp_lines():
    s = scene_initial()
    fold_scene(["|t:|1700000000"], s)
    assert s == scene_initial()


def test_fold_scene_split_block_projected_correctly():
    """Fold_scene works on PROJECTED lines (split blocks already resolved)."""
    raw = [
        "|split|p2",
        "|-damage|p2a: Rotom|88/250",
        "|-damage|p2a: Rotom|35/100",
    ]
    projected_p1 = project_frame(raw, side="p1")  # owner p1 sees public twin for p2
    s = scene_initial()
    fold_scene(projected_p1, s)
    # p1 sees the PUBLIC line 35/100 for the opponent
    assert abs(s["p2"]["hpFrac"] - 0.35) < 1e-6


# ── extract_trace_lines ───────────────────────────────────────────────────────


def test_extract_trace_empty_on_no_reasoning():
    lines = ["|move|p1a: Garchomp|Earthquake|p2a: Rotom", "|-damage|p2a: Rotom|35/100"]
    assert extract_trace_lines(lines) == []


def test_extract_trace_reasoning_line():
    lines = ["|-reasoning|p1|Earthquake hits both — best damage output"]
    result = extract_trace_lines(lines)
    assert len(result) == 1
    assert result[0]["side"] == "p1"
    assert "Earthquake" in result[0]["text"]


def test_extract_trace_say_line():
    lines = ["|say|p2|I'll resist that!"]
    result = extract_trace_lines(lines)
    assert result[0]["side"] == "p2"
    assert "resist" in result[0]["text"]


def test_extract_trace_multiple_lines():
    lines = [
        "|-reasoning|p1|Stealth Rocks for chip",
        "|move|p1a: Garchomp|Stealth Rock|p2a: Rotom",
        "|-reasoning|p1|Predict switch next turn",
    ]
    result = extract_trace_lines(lines)
    assert len(result) == 2
    assert result[0]["text"] == "Stealth Rocks for chip"
    assert result[1]["text"] == "Predict switch next turn"


def test_extract_trace_non_reasoning_not_included():
    lines = ["|-damage|p1a: Garchomp|100/298", "|move|p1a: Garchomp|Earthquake|p2a: Rotom"]
    assert extract_trace_lines(lines) == []
