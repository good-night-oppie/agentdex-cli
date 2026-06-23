"""Tests for HarnessPlayer doubles-decision support (GA-SELFPLAY-EVOLVE).

Offline tests for the doubles-defer path: ``HarnessPlayer.choose_move`` now
detects a ``DoubleBattle`` via shape probe (``_is_doubles_battle``) and routes
ALL strategies through poke-env's ``choose_random_move`` on doubles, because ``valid_orders``
is nested per active slot on doubles while
``available_moves`` is shape-shifted (``list[list[Move]]`` on doubles vs
``list[Move]`` on singles), which would misfeed ``max_base_power_choice`` /
``select_codex_move``.

Uses fake battle objects (poke-env imports are heavy + a real ``Battle`` needs a
running PS server), so the tests stay offline + fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adx_showdown.selfplay.runner import _is_doubles_battle

# ---------------------------------------------------------------- shape probe


@dataclass
class _FakeSinglesBattle:
    """Minimal singles shape: bool ``force_switch`` + flat ``available_moves``."""

    force_switch: bool = False
    available_moves: list = field(default_factory=list)
    valid_orders: list = field(default_factory=list)
    turn: int = 1


@dataclass
class _FakeDoublesBattle:
    """Minimal doubles shape: ``list[bool]`` ``force_switch`` + nested moves."""

    force_switch: list = field(default_factory=lambda: [False, False])
    available_moves: list = field(default_factory=lambda: [[], []])
    valid_orders: list = field(default_factory=list)
    turn: int = 1


def test_singles_battle_is_not_doubles():
    b = _FakeSinglesBattle()
    assert _is_doubles_battle(b) is False
    b2 = _FakeSinglesBattle(force_switch=True, available_moves=["move-a"])
    assert _is_doubles_battle(b2) is False


def test_doubles_battle_detected_via_force_switch_list():
    b = _FakeDoublesBattle()  # force_switch=[False, False]
    assert _is_doubles_battle(b) is True


def test_doubles_battle_detected_via_nested_available_moves():
    # Defensive: if force_switch happens to be missing/None (some test stubs),
    # available_moves shape alone catches it.
    class _Probe:
        force_switch = None
        available_moves = [["m1", "m2"], ["m3"]]

    assert _is_doubles_battle(_Probe()) is True


def test_empty_doubles_moves_still_detected_via_force_switch():
    # Forced-switch doubles: both slots have available_moves=[] but
    # force_switch=[bool,bool] still flags via the list-shape check.
    b = _FakeDoublesBattle(force_switch=[True, False], available_moves=[[], []])
    assert _is_doubles_battle(b) is True


def test_missing_attributes_default_to_singles():
    # A bare object with no force_switch / no available_moves doesn't match the
    # doubles shape — defaults to singles (the safer fallback: singles paths
    # don't crash on doubles input, just sample sub-optimally).
    class _Bare:
        pass

    assert _is_doubles_battle(_Bare()) is False


# ---------------------------------------------------------------- routing
#
# An end-to-end behavioral test against a real ``HarnessPlayer`` would need
# poke-env websocket scaffolding; the shape-probe tests above are the offline
# contract for ``_is_doubles_battle`` — the only routing seam in
# ``choose_move``. ``test_selfplay_runner.py`` covers that the doubles branch
# calls poke-env's ``choose_random_move`` instead of the singles-only seeded
# order sampler. Bridge tests in ``test_selfplay_mode_bridge.py`` cover that
# doubles formats are no longer rejected at the format-resolution layer. Live
# doubles verification belongs to the next increment (live PS-server e2e).
