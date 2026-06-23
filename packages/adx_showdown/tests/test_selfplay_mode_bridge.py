"""Tests for the arena-mode → runner battle_format bridge (GA-SELFPLAY-EVOLVE).

``battle_format_for_mode`` lets the runner be driven by arena mode instead of a
raw format string. Pure resolution (no poke-env battle), so it runs offline.
"""

import pytest
from adx_showdown.selfplay import team_modes as tm
from adx_showdown.selfplay.runner import DEFAULT_FORMAT, battle_format_for_mode


def test_mode_none_is_passthrough():
    assert battle_format_for_mode(None) == DEFAULT_FORMAT
    assert battle_format_for_mode(None, "gen9ou") == "gen9ou"


def test_team_mode_resolves_to_a_doubles_format():
    fmt = battle_format_for_mode("team")
    assert tm.FORMATS[fmt].topology == tm.DOUBLES


def test_singles_modes_resolve_to_singles():
    for mode in ("solo_bots", "pvp", "selfplay"):
        assert tm.FORMATS[battle_format_for_mode(mode)].topology == tm.SINGLES


def test_non_default_battle_format_is_a_topology_checked_override():
    # team + a valid doubles override → that format
    assert battle_format_for_mode("team", "gen9vgc2024regh") == "gen9vgc2024regh"
    # team + a singles override → rejected (would drop the 2nd agent)
    with pytest.raises(tm.UnsupportedFormat):
        battle_format_for_mode("team", "gen9ou")


def test_unknown_mode_raises():
    with pytest.raises(tm.UnknownMode):
        battle_format_for_mode("nope")
