"""Deterministic in-repo fake engines for ``adx measure --engine-fake``.

NOT-FOR-LEADERBOARD
-------------------
These fakes exist so the end-to-end ``adx measure`` path is demonstrable
before real ARC / Harbor clients land. Receipts produced under
``--engine-fake`` MUST be forced by the CLI to
``tier=self_reported`` / ``kind=fake_engine`` — a fake run can never claim
a verified receipt or appear on a leaderboard.
"""

from __future__ import annotations

from typing import Any

from adx_ladders.adapters.tb2_harbor import HarborTaskResult

# Marker baked into fake artifact paths so audits can grep for demos.
_FAKE_MARKER = "NOT-FOR-LEADERBOARD"


class FakeArcEngine:
    """Deterministic ARC-AGI-3 engine stub. NOT-FOR-LEADERBOARD."""

    def __init__(self, *, quality: float = 0.42, steps_to_done: int = 1) -> None:
        self._quality = quality
        self._steps_to_done = steps_to_done
        self._step = 0
        self._game: str | None = None

    def reset(self, game_id: str) -> dict[str, Any]:
        self._game = game_id
        self._step = 0
        return {
            "frame": {"grid": [[0]], "game": game_id, "marker": _FAKE_MARKER},
            "done": False,
        }

    def step(self, action: Any) -> dict[str, Any]:
        self._step += 1
        done = self._step >= self._steps_to_done
        return {
            "frame": {
                "grid": [[1]],
                "last_action": action,
                "game": self._game,
                "marker": _FAKE_MARKER,
            },
            "done": done,
        }

    def score(self) -> float:
        return self._quality

    def scorecard_id(self) -> str | None:
        # Never return a scorecard id — verified receipts are forbidden for fakes.
        return None


class FakeHarbor:
    """Deterministic Harbor stub for TB2. NOT-FOR-LEADERBOARD."""

    def __init__(
        self,
        *,
        tasks: list[str] | None = None,
        pass_rate: float = 2 / 3,
    ) -> None:
        self._tasks = list(tasks) if tasks is not None else ["t0", "t1", "t2"]
        n = len(self._tasks)
        n_pass = int(round(pass_rate * n)) if n else 0
        self._passed = {tid: (i < n_pass) for i, tid in enumerate(self._tasks)}

    def list_tasks(self, suite: str) -> list[str]:
        del suite  # suite forwarded by adapter; fake ignores content
        return list(self._tasks)

    def run_task(
        self,
        task_id: str,
        agent_cmd: str,
        timeout_sec: float,
    ) -> HarborTaskResult:
        del agent_cmd, timeout_sec
        passed = bool(self._passed.get(task_id, False))
        return HarborTaskResult(
            passed=passed,
            log_path=f"/tmp/fake-harbor-{task_id}-{_FAKE_MARKER}.log",
            cost_dollar=0.01,
            timed_out=False,
        )
