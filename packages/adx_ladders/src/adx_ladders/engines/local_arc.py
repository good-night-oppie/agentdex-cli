"""Deterministic local ARC-style grid engine (genuine dynamics, no SDK).

NOT leaderboard-eligible
------------------------
``scorecard_id()`` always returns ``None``. Local runs are self-reported
only — there is no third-party scorecard authority. Quality is derived from
real agent/goal geometry on a seeded grid, not a hardcoded stub score.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

# Cell markers in the observation grid.
_EMPTY = 0
_AGENT = 1
_GOAL = 2
_WALL = 3

_ACTION_DELTA: dict[str, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
    "n": (-1, 0),
    "s": (1, 0),
    "w": (0, -1),
    "e": (0, 1),
}


def _seed_from_game_id(game_id: str) -> int:
    digest = hashlib.sha256(game_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class LocalArcEngine:
    """Navigate an agent cell to a goal cell on a fixed seeded grid.

    Outcome is determined by the action sequence the candidate sends.
    Quality is normalized progress toward (or reaching) the goal in ``[0, 1]``.
    Across multiple ``reset`` episodes, ``score()`` returns the mean of
    per-episode qualities.
    """

    def __init__(self, *, grid_size: int = 5, max_walls: int = 0) -> None:
        if grid_size < 3:
            raise ValueError("grid_size must be >= 3")
        self._size = grid_size
        self._max_walls = max(0, max_walls)
        self._grid: list[list[int]] = []
        self._agent: tuple[int, int] = (0, 0)
        self._goal: tuple[int, int] = (0, 0)
        self._initial_dist = 0
        self._best_dist = 0
        self._done = False
        self._game_id: str | None = None
        self._episode_qualities: list[float] = []
        self._episode_scored = False

    def reset(self, game_id: str) -> Mapping[str, Any]:
        # Finalize any open episode before starting a new one.
        self._finalize_episode_if_needed()

        rng_state = _seed_from_game_id(game_id)
        self._game_id = game_id
        self._done = False
        self._episode_scored = False

        cells = [(r, c) for r in range(self._size) for c in range(self._size)]
        agent_idx = rng_state % len(cells)
        self._agent = cells.pop(agent_idx)
        goal_idx = (rng_state // 7) % len(cells)
        self._goal = cells.pop(goal_idx)

        # Optional walls stay outside the agent↔goal bounding box so a
        # greedy manhattan policy remains solvable (open-grid default).
        walls: set[tuple[int, int]] = set()
        r_lo, r_hi = sorted((self._agent[0], self._goal[0]))
        c_lo, c_hi = sorted((self._agent[1], self._goal[1]))
        outside = [(r, c) for (r, c) in cells if not (r_lo <= r <= r_hi and c_lo <= c <= c_hi)]
        n_walls = min(self._max_walls, len(outside))
        cursor = rng_state
        for _ in range(n_walls):
            cursor = (cursor * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
            idx = cursor % len(outside)
            walls.add(outside.pop(idx))

        self._grid = [[_EMPTY] * self._size for _ in range(self._size)]
        for wr, wc in walls:
            self._grid[wr][wc] = _WALL
        self._grid[self._agent[0]][self._agent[1]] = _AGENT
        self._grid[self._goal[0]][self._goal[1]] = _GOAL

        self._initial_dist = _manhattan(self._agent, self._goal)
        self._best_dist = self._initial_dist
        if self._initial_dist == 0:
            self._done = True
            self._best_dist = 0

        return {"frame": self._frame(), "done": self._done}

    def step(self, action: Any) -> Mapping[str, Any]:
        if self._done:
            return {"frame": self._frame(), "done": True}

        key = str(action).strip() if action is not None else ""
        delta = _ACTION_DELTA.get(key)
        if delta is None:
            # Unknown action: no-op (still advances the episode clock in the
            # adapter); quality unchanged.
            return {"frame": self._frame(), "done": False}

        nr = self._agent[0] + delta[0]
        nc = self._agent[1] + delta[1]
        if not (0 <= nr < self._size and 0 <= nc < self._size):
            return {"frame": self._frame(), "done": False}
        if self._grid[nr][nc] == _WALL:
            return {"frame": self._frame(), "done": False}

        # Clear old agent cell (restore goal marker if we leave the goal —
        # we never occupy goal without finishing, so just clear to empty).
        ar, ac = self._agent
        self._grid[ar][ac] = _EMPTY
        self._agent = (nr, nc)
        if self._agent == self._goal:
            self._grid[nr][nc] = _GOAL
            self._best_dist = 0
            self._done = True
        else:
            self._grid[nr][nc] = _AGENT
            dist = _manhattan(self._agent, self._goal)
            if dist < self._best_dist:
                self._best_dist = dist

        return {"frame": self._frame(), "done": self._done}

    def score(self) -> float:
        self._finalize_episode_if_needed()
        if not self._episode_qualities:
            return 0.0
        return sum(self._episode_qualities) / len(self._episode_qualities)

    def scorecard_id(self) -> str | None:
        return None

    def _episode_quality(self) -> float:
        if self._initial_dist <= 0:
            return 1.0
        # Normalized progress using best distance achieved this episode.
        progress = (self._initial_dist - self._best_dist) / self._initial_dist
        if progress < 0.0:
            return 0.0
        if progress > 1.0:
            return 1.0
        return float(progress)

    def _finalize_episode_if_needed(self) -> None:
        if self._game_id is None or self._episode_scored:
            return
        self._episode_qualities.append(self._episode_quality())
        self._episode_scored = True

    def _frame(self) -> dict[str, Any]:
        return {
            "grid": [row[:] for row in self._grid],
            "agent": [self._agent[0], self._agent[1]],
            "goal": [self._goal[0], self._goal[1]],
            "size": self._size,
            "game": self._game_id,
        }
