"""Held-out baseline opponents for self-play fitness (ADR-0014 / SPEC Lane A3).

The meta-harness loop is only honest if the evolved harness is scored against
opponents it cannot have over-fit — so win-rate / Elo are measured vs a FIXED,
held-out set of poke-env baselines, never vs the self-play pool. We port the
three canonical poke-env example players (the same difficulty ladder the arena's
own scripted bots follow, ``random < max-damage < heuristic``):

  - ``RandomPlayer``          — poke-env built-in: a uniform-random legal move.
  - ``MaxBasePowerPlayer``    — our port of the decision seam (poke-env has no
                                built-in): pick the highest-base-power move.
  - ``SimpleHeuristicsPlayer``— poke-env built-in: type/stat-aware heuristics.

This module is import-safe WITHOUT poke-env: the registry metadata (names +
calibration anchor Elos) and the pure ``max_base_power_choice`` decision logic
carry zero poke-env dependency, so the fitness function and its tests never pull
in the heavy, server-coupled battle library. Only ``build_baseline`` — which
constructs a live ``poke_env.Player`` for the runner — imports poke-env, lazily,
and fails with a clear message if it is absent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

RANDOM_PLAYER = "RandomPlayer"
MAX_BASE_POWER_PLAYER = "MaxBasePowerPlayer"
SIMPLE_HEURISTICS_PLAYER = "SimpleHeuristicsPlayer"

# Provisional calibration anchors reflecting poke-env's documented difficulty
# ordering Random < MaxBasePower < SimpleHeuristics (matches adx_showdown
# bots.py "intended ordering random < max-damage < heuristic"). These are the
# opponent ratings the fitness performance-rating math anchors on; Lane D
# calibration (non-overlapping 2·RD self-test) can refine the exact numbers.
ANCHOR_ELO: dict[str, float] = {
    RANDOM_PLAYER: 1000.0,
    MAX_BASE_POWER_PLAYER: 1300.0,
    SIMPLE_HEURISTICS_PLAYER: 1500.0,
}


@dataclass(frozen=True)
class BaselineSpec:
    """One held-out baseline: its canonical poke-env name, the calibration
    anchor Elo the fitness math rates against, whether poke-env ships it
    (``builtin``) or we port it, and a one-line description."""

    name: str
    anchor_elo: float
    builtin: bool
    description: str


HELD_OUT_BASELINES: dict[str, BaselineSpec] = {
    RANDOM_PLAYER: BaselineSpec(
        RANDOM_PLAYER, ANCHOR_ELO[RANDOM_PLAYER], True, "uniform random legal move"
    ),
    MAX_BASE_POWER_PLAYER: BaselineSpec(
        MAX_BASE_POWER_PLAYER,
        ANCHOR_ELO[MAX_BASE_POWER_PLAYER],
        False,
        "highest base-power available move (decision-seam port)",
    ),
    SIMPLE_HEURISTICS_PLAYER: BaselineSpec(
        SIMPLE_HEURISTICS_PLAYER,
        ANCHOR_ELO[SIMPLE_HEURISTICS_PLAYER],
        True,
        "poke-env type/stat-aware heuristics",
    ),
}


def baseline_names() -> list[str]:
    """The held-out baseline names in difficulty order (weakest first)."""
    return list(HELD_OUT_BASELINES)


def anchor_elo(name: str) -> float:
    """Calibration anchor Elo for a held-out baseline. Raises KeyError on an
    unknown name (callers must not silently default an unrecognized opponent
    to a fabricated rating)."""
    return HELD_OUT_BASELINES[name].anchor_elo


def max_base_power_choice(available_moves: Iterable[Any]) -> Any | None:
    """The MaxBasePower decision seam, as a pure function (no poke-env, no
    battle object) so it is unit-testable on its own.

    Picks the move with the highest ``base_power`` (missing/None power counts as
    0); ties resolve to the first such move (``max`` is stable). Returns ``None``
    when no moves are available (the caller falls back to a random choice)."""
    moves = list(available_moves or [])
    if not moves:
        return None
    return max(moves, key=lambda m: getattr(m, "base_power", 0) or 0)


def build_baseline(name: str, **player_kwargs: Any) -> Any:
    """Construct the live ``poke_env.Player`` for a held-out baseline (used by the
    Lane-A runner against a live PS server).

    Lazily imports poke-env — a heavy, server-coupled dependency the fitness path
    never needs — and raises a clear ``RuntimeError`` if it is not installed.
    ``RandomPlayer`` / ``SimpleHeuristicsPlayer`` are poke-env built-ins;
    ``MaxBasePowerPlayer`` is defined here (poke-env ships no equivalent) as a
    thin ``Player`` whose ``choose_move`` delegates to ``max_base_power_choice``.
    """
    if name not in HELD_OUT_BASELINES:
        raise KeyError(f"unknown held-out baseline {name!r}; known: {baseline_names()}")
    try:
        from poke_env.player import Player, RandomPlayer, SimpleHeuristicsPlayer
    except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "poke-env is required to build a live baseline player but is not "
            "installed (it is intentionally absent from the fitness path). "
            "Install it in the runner's environment (ADR-0014 Phase 1)."
        ) from e

    if name == RANDOM_PLAYER:
        return RandomPlayer(**player_kwargs)
    if name == SIMPLE_HEURISTICS_PLAYER:
        return SimpleHeuristicsPlayer(**player_kwargs)

    class MaxBasePowerPlayer(Player):
        """Port of the ADR-0014 decision seam: highest-base-power move."""

        def choose_move(self, battle: Any) -> Any:
            move = max_base_power_choice(getattr(battle, "available_moves", None))
            if move is not None:
                return self.create_order(move)
            return self.choose_random_move(battle)

    return MaxBasePowerPlayer(**player_kwargs)


__all__ = [
    "RANDOM_PLAYER",
    "MAX_BASE_POWER_PLAYER",
    "SIMPLE_HEURISTICS_PLAYER",
    "ANCHOR_ELO",
    "BaselineSpec",
    "HELD_OUT_BASELINES",
    "baseline_names",
    "anchor_elo",
    "max_base_power_choice",
    "build_baseline",
]
