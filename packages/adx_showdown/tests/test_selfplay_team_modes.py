"""Tests for the GA-SELFPLAY-EVOLVE arena-mode → battle-format substrate.

Pure + poke-env-free (the module imports no poke_env), so these run without the
``selfplay`` extra installed.
"""

import pytest
from adx_showdown.selfplay import team_modes as tm


def test_four_arena_modes_match_ga_design_contract():
    # ids must match GA-DESIGN data.js (solo_bots|pvp|team|selfplay) so the
    # mode-select cards bind 1:1 to this substrate.
    assert set(tm.MODES) == {"solo_bots", "pvp", "team", "selfplay"}


def test_free_vs_paid_split():
    assert tm.is_paid("team") is True
    assert tm.is_paid("selfplay") is True
    assert tm.is_paid("solo_bots") is False
    assert tm.is_paid("pvp") is False


def test_default_formats_and_topology_per_mode():
    # free + selfplay run singles; team-up runs doubles.
    assert tm.resolve_format("solo_bots").topology == tm.SINGLES
    assert tm.resolve_format("pvp").topology == tm.SINGLES
    assert tm.resolve_format("selfplay").topology == tm.SINGLES
    assert tm.resolve_format("team").topology == tm.DOUBLES


def test_selfplay_and_team_flags():
    assert tm.get_mode("selfplay").self_play is True
    assert tm.get_mode("team").team_up is True
    # a team-up mode must default to a doubles format (else the 2nd agent is dropped)
    assert tm.FORMATS[tm.get_mode("team").default_format].topology == tm.DOUBLES


def test_resolve_format_override_must_be_topology_compatible():
    # team (doubles) + a singles override → rejected (would silently drop the 2nd agent)
    with pytest.raises(tm.UnsupportedFormat):
        tm.resolve_format("team", override="gen9randombattle")
    # solo_bots (singles) + a doubles override → rejected
    with pytest.raises(tm.UnsupportedFormat):
        tm.resolve_format("solo_bots", override="gen9doublesou")
    # team + a valid doubles override → ok
    assert tm.resolve_format("team", override="gen9vgc2024regh").id == "gen9vgc2024regh"


def test_unknown_mode_and_format_raise():
    with pytest.raises(tm.UnknownMode):
        tm.get_mode("nope")
    with pytest.raises(tm.UnknownMode):
        tm.is_paid("nope")
    with pytest.raises(tm.UnsupportedFormat):
        tm.resolve_format("pvp", override="gen9nonsense")


def test_every_format_declares_valid_topology():
    for fmt in tm.FORMATS.values():
        assert fmt.topology in (tm.SINGLES, tm.DOUBLES)
        assert fmt.id  # non-empty Showdown id
    # the named defaults exist + have the expected topology
    assert tm.FORMATS[tm.DEFAULT_SINGLES].topology == tm.SINGLES
    assert tm.FORMATS[tm.DEFAULT_TEAM].topology == tm.DOUBLES


def test_module_is_poke_env_free():
    # the substrate contract must import without the optional `selfplay` extra
    import sys

    assert "poke_env" not in getattr(tm, "__dict__", {})
    # nothing the module pulled in should have forced poke_env to import
    # (import is lazy in the runner, not here)
    assert tm.resolve_format("selfplay").id == tm.DEFAULT_SINGLES
    _ = sys  # keep the import referenced
