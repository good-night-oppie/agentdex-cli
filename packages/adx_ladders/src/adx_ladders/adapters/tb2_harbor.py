"""Terminal-Bench 2 (tb2) ladder run-adapter via Harbor (ADR-0015 D3/D4/D5/D6).

Out-of-process Harbor execution
-------------------------------
The candidate ``entrypoint`` is passed as the agent command to an injected
``HarborProtocol``. The real Harbor CLI / SDK is NOT imported here — callers
inject a protocol implementation (local fake in unit tests; real Harbor
wrapper in a later integration WU).

Budget division (v1 equal split)
--------------------------------
``candidate.budget.wall_clock_min`` is converted to seconds and divided
equally across the suite's tasks::

    per_task_timeout_sec = (wall_clock_min * 60.0) / n_tasks

A task that exceeds its slice is killed by the protocol, counted as failed
(``passed=False``), and reported honestly in the run-summary JSON — never
dropped. Remaining tasks still run (their own slices are independent).

Scores
------
- ``quality``: pass rate in ``[0, 1]`` (passed / n_tasks; ``0.0`` if empty).
- ``cost_dollar``: sum of per-task ``HarborTaskResult.cost_dollar`` when every
  task reports a measured cost; otherwise the declared ``budget.usd``.
- ``wall_clock_sec``: measured wall clock of the full ``measure`` call.

Receipt (D6, static lane)
-------------------------
TB2 has no third-party receipt authority. Every run emits
``Receipt(tier="self_reported", kind="raw_artifacts", ...)`` whose artifacts
are the on-disk run-summary JSON (per-task pass/fail + timing under
``candidate/.adx/runs/...``) plus Harbor log paths as reported.
"""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from adx_frontier.candidate import AgentCandidate
from adx_ladders.base import LadderAdapter, LadderClass, MeasureResult, Receipt


@dataclass(frozen=True)
class HarborTaskResult:
    """Outcome of one Harbor task run.

    ``cost_dollar`` is optional: when present on every task in a suite, the
    adapter aggregates measured cost; otherwise scores fall back to the
    candidate's declared ``budget.usd``.
    """

    passed: bool
    log_path: str
    cost_dollar: float | None = None
    timed_out: bool = False


class HarborProtocol(Protocol):
    """Thin Harbor surface — no network assumed; real client is injected later."""

    def run_task(
        self,
        task_id: str,
        agent_cmd: str,
        timeout_sec: float,
    ) -> HarborTaskResult:
        """Execute ``agent_cmd`` on ``task_id``; kill at ``timeout_sec``."""

    def list_tasks(self, suite: str) -> list[str]:
        """Return task ids for ``suite``."""


class Tb2HarborAdapter(LadderAdapter):
    """Run an AgentCandidate against Terminal-Bench 2 via injected Harbor."""

    ladder_id = "tb2"
    ladder_class = LadderClass.STATIC

    def __init__(
        self,
        harbor: HarborProtocol,
        *,
        suite: str = "default",
        cost_dollar: float | None = None,
    ) -> None:
        self._harbor = harbor
        self._suite = suite
        self._cost_dollar = cost_dollar

    def measure(self, candidate: AgentCandidate) -> MeasureResult:
        """Run the TB2 suite; equal-split wall-clock across tasks (see module doc)."""
        self.pre_run_check(candidate)

        task_ids: Sequence[str] = tuple(self._harbor.list_tasks(self._suite))
        n_tasks = len(task_ids)
        budget_sec = float(candidate.budget.wall_clock_min) * 60.0
        # Equal split: each task gets the same wall-clock slice. A task that
        # exceeds its slice is killed by HarborProtocol and counted failed.
        per_task_timeout_sec = (budget_sec / n_tasks) if n_tasks else budget_sec

        started = time.monotonic()
        task_records: list[dict[str, object]] = []
        measured_costs: list[float] = []
        all_costs_measured = n_tasks > 0

        for task_id in task_ids:
            task_started = time.monotonic()
            result = self._harbor.run_task(
                task_id,
                candidate.entrypoint,
                per_task_timeout_sec,
            )
            task_elapsed = max(time.monotonic() - task_started, 0.0)
            timed_out = bool(result.timed_out) or (
                not result.passed and task_elapsed >= per_task_timeout_sec
            )
            task_records.append(
                {
                    "task_id": task_id,
                    "passed": bool(result.passed),
                    "timed_out": timed_out,
                    "wall_clock_sec": task_elapsed,
                    "timeout_sec": per_task_timeout_sec,
                    "log_path": result.log_path,
                }
            )
            if result.cost_dollar is None:
                all_costs_measured = False
            else:
                measured_costs.append(float(result.cost_dollar))

        wall_clock_sec = max(time.monotonic() - started, 0.0)
        n_passed = sum(1 for rec in task_records if rec["passed"])
        quality = (n_passed / n_tasks) if n_tasks else 0.0

        if self._cost_dollar is not None:
            cost = float(self._cost_dollar)
        elif all_costs_measured:
            cost = float(sum(measured_costs))
        else:
            # Protocol did not report per-task cost → declared budget.
            cost = float(candidate.budget.usd)

        summary_ref = self._write_run_summary(
            candidate=candidate,
            task_records=task_records,
            quality=quality,
            cost_dollar=cost,
            wall_clock_sec=wall_clock_sec,
            per_task_timeout_sec=per_task_timeout_sec,
        )

        log_paths = tuple(
            str(rec["log_path"])
            for rec in task_records
            if rec["log_path"]
        )
        artifacts = (str(summary_ref),) + log_paths

        receipt = Receipt(
            tier="self_reported",
            kind="raw_artifacts",
            ref="",
            artifacts=artifacts,
        )

        return MeasureResult(
            scores={
                "quality": quality,
                "cost_dollar": cost,
                "wall_clock_sec": wall_clock_sec,
            },
            receipt=receipt,
            ladder_id=self.ladder_id,
            base_model=candidate.base_model,
            budget_usd=candidate.budget.usd,
            budget_wall_clock_min=candidate.budget.wall_clock_min,
        )

    def _write_run_summary(
        self,
        *,
        candidate: AgentCandidate,
        task_records: list[dict[str, object]],
        quality: float,
        cost_dollar: float,
        wall_clock_sec: float,
        per_task_timeout_sec: float,
    ) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"tb2-{stamp}-{uuid.uuid4().hex[:8]}.json"
        payload = {
            "ladder_id": self.ladder_id,
            "ladder_class": self.ladder_class.value,
            "candidate": candidate.name,
            "suite": self._suite,
            "tasks": task_records,
            "scores": {
                "quality": quality,
                "cost_dollar": cost_dollar,
                "wall_clock_sec": wall_clock_sec,
            },
            "timing": {
                "wall_clock_sec": wall_clock_sec,
                "budget_wall_clock_min": candidate.budget.wall_clock_min,
                "per_task_timeout_sec": per_task_timeout_sec,
                "division": "equal_split",
            },
        }
        text = json.dumps(payload, indent=2) + "\n"

        # Prefer candidate/.adx/runs; fall back to temp / in-memory so a
        # read-only candidate root cannot crash measure() (honest, not dropped).
        primary = candidate.root / ".adx" / "runs"
        try:
            primary.mkdir(parents=True, exist_ok=True)
            path = primary / filename
            path.write_text(text, encoding="utf-8")
            return str(path.resolve())
        except OSError:
            pass
        try:
            tmp = Path(tempfile.mkdtemp(prefix="adx-tb2-runs-"))
            path = tmp / filename
            path.write_text(text, encoding="utf-8")
            return str(path.resolve())
        except OSError:
            pass
        return f"memory://{filename}"
