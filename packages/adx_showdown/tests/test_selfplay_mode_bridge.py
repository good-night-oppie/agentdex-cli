"""Tests for the arena-mode → runner battle_format bridge (GA-SELFPLAY-EVOLVE).

``battle_format_for_mode`` lets the runner be driven by arena mode instead of a
raw format string. Pure resolution (no poke-env battle), so it runs offline.

The bridge has TWO guard layers: the substrate (``team_modes``) rejects unknown
modes + topology-incompatible overrides, and the *runner-level* guard refuses
formats the player can't drive yet (doubles + ``team_required``) — see Codex
review on PR #485: enabling team mode while ``HarnessPlayer`` is singles-only
would silently produce broken matchups.
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


def test_team_mode_blocked_until_doubles_decision_lands():
    # The substrate-level resolve_format STILL returns the doubles format (the
    # contract stays honest); the runner-level bridge refuses because the player
    # can't drive doubles yet. Codex P1 fix.
    assert tm.resolve_format("team").topology == tm.DOUBLES
    with pytest.raises(RunnerNotReadyForFormat, match="doubles"):
        battle_format_for_mode("team")


def test_doubles_override_blocked_until_doubles_decision_lands():
    # A valid doubles OVERRIDE on a doubles-mode would expose the singles-only
    # player, so the runner-level guard fires.
    with pytest.raises(RunnerNotReadyForFormat, match="doubles"):
        battle_format_for_mode("team", "gen9randomdoublesbattle")


def test_team_required_singles_override_blocked_until_teambuilder_lands():
    # Codex P2 #3: ``gen9ou`` is singles + team_required; the doubles guard
    # passes, the team-builder guard fires (no team= kwarg into the players).
    with pytest.raises(RunnerNotReadyForFormat, match="team-required"):
        battle_format_for_mode("solo_bots", "gen9ou")


def test_team_required_doubles_override_blocked():
    # ``gen9vgc2024regh`` is doubles + team_required; the doubles guard fires
    # first (it's the bigger blocker).
    with pytest.raises(RunnerNotReadyForFormat, match="doubles"):
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
