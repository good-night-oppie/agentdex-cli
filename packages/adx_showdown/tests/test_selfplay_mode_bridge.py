"""Tests for the arena-mode → runner battle_format bridge (GA-SELFPLAY-EVOLVE).

``battle_format_for_mode`` lets the runner be driven by arena mode instead of a
raw format string. Pure resolution (no poke-env battle), so it runs offline.

The bridge has TWO guard layers: the substrate (``team_modes``) rejects unknown
modes + topology-incompatible overrides, and the *runner-level* guard refuses
formats the runner can't drive yet (``team_required`` — no team-builder wired).
The doubles topology rail used to also be guarded; that guard was LIFTED in this
increment because ``HarnessPlayer.choose_move`` now drives doubles via the
topology-agnostic ``valid_orders`` path (see ``_is_doubles_battle`` deferral).
"""

import pytest
from adx_showdown.selfplay import team_modes as tm
from adx_showdown.selfplay.runner import (
    DEFAULT_FORMAT,
    RunnerNotReadyForFormat,
    battle_format_for_mode,
)


def test_mode_none_is_passthrough():
    assert battle_format_for_mode(None) == DEFAULT_FORMAT
    assert battle_format_for_mode(None, "gen9ou") == "gen9ou"


def test_singles_modes_resolve_to_singles():
    for mode in ("solo_bots", "pvp", "selfplay"):
        assert tm.FORMATS[battle_format_for_mode(mode)].topology == tm.SINGLES


def test_team_mode_resolves_to_doubles_format():
    # The doubles guard was LIFTED — HarnessPlayer.choose_move now defers to the
    # seeded random path on a DoubleBattle (valid_orders returns DoubleBattleOrder
    # transparently). The substrate-level resolve_format stays honest.
    assert tm.resolve_format("team").topology == tm.DOUBLES
    assert battle_format_for_mode("team") == tm.DEFAULT_TEAM  # gen9randomdoublesbattle


def test_doubles_override_now_allowed():
    # A valid doubles OVERRIDE on a doubles-mode is now allowed; the player
    # handles it via the doubles-defer path.
    assert battle_format_for_mode("team", "gen9randomdoublesbattle") == "gen9randomdoublesbattle"


def test_team_required_singles_override_blocked_until_teambuilder_lands():
    # ``gen9ou`` is singles + team_required; the team-builder guard still fires
    # (no team= kwarg into the players).
    with pytest.raises(RunnerNotReadyForFormat, match="team-required"):
        battle_format_for_mode("solo_bots", "gen9ou")


def test_team_required_doubles_override_blocked():
    # ``gen9vgc2024regh`` is doubles + team_required; doubles no longer guards,
    # but team_required still does.
    with pytest.raises(RunnerNotReadyForFormat, match="team-required"):
        battle_format_for_mode("team", "gen9vgc2024regh")


def test_non_default_singles_override_is_substrate_topology_checked():
    # team + a singles override is rejected at the SUBSTRATE layer (would drop
    # the 2nd agent) — fires before the runner guard, so the exception type
    # stays ``UnsupportedFormat`` not ``RunnerNotReadyForFormat``.
    with pytest.raises(tm.UnsupportedFormat):
        battle_format_for_mode("team", "gen9ou")


def test_unknown_mode_raises():
    with pytest.raises(tm.UnknownMode):
        battle_format_for_mode("nope")
