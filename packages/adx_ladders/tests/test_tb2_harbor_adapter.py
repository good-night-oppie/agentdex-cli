"""Unit tests for Tb2HarborAdapter — fakes only, no network."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import yaml

from adx_frontier.candidate import FRONTIER_AXES, load_candidate
from adx_ladders.adapters.tb2_harbor import (
    HarborTaskResult,
    Tb2HarborAdapter,
)
from adx_ladders.base import LadderClass


class _FakeHarbor:
    """In-memory Harbor stub for unit tests."""

    def __init__(
        self,
        *,
        tasks: list[str] | None = None,
        outcomes: dict[str, HarborTaskResult] | None = None,
        sleep_sec: float = 0.0,
    ) -> None:
        self._tasks = list(tasks) if tasks is not None else ["t0", "t1", "t2"]
        self._outcomes = dict(outcomes or {})
        self._sleep_sec = sleep_sec
        self.calls: list[tuple[str, str, float]] = []

    def list_tasks(self, suite: str) -> list[str]:
        assert suite  # suite is forwarded; content unused by fake
        return list(self._tasks)

    def run_task(
        self,
        task_id: str,
        agent_cmd: str,
        timeout_sec: float,
    ) -> HarborTaskResult:
        self.calls.append((task_id, agent_cmd, timeout_sec))
        if self._sleep_sec > 0:
            time.sleep(self._sleep_sec)
        if task_id in self._outcomes:
            return self._outcomes[task_id]
        log = f"/tmp/harbor-{task_id}.log"
        return HarborTaskResult(passed=True, log_path=log)


def _write_candidate(
    tmp_path: Path,
    *,
    ladders: list[str] | None = None,
    wall_clock_min: float = 3.0,
    usd: float = 2.5,
    entrypoint: str | None = None,
) -> Path:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "noop.py").write_text("# noop\n", encoding="utf-8")
    agent = tmp_path / "agent.py"
    agent.write_text("print('tb2-agent')\n", encoding="utf-8")

    manifest = {
        "name": "tb2-fake-agent",
        "entrypoint": entrypoint or f"{sys.executable} agent.py",
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": usd, "wall_clock_min": wall_clock_min},
        "ladders": ladders if ladders is not None else ["tb2", "arc-agi-3"],
    }
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def test_happy_path_pass_rate_and_summary(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path)
    candidate = load_candidate(root)
    harbor = _FakeHarbor(
        tasks=["a", "b", "c"],
        outcomes={
            "a": HarborTaskResult(passed=True, log_path="/tmp/a.log"),
            "b": HarborTaskResult(passed=True, log_path="/tmp/b.log"),
            "c": HarborTaskResult(passed=False, log_path="/tmp/c.log"),
        },
    )
    adapter = Tb2HarborAdapter(harbor, suite="tb2-lite")

    result = adapter.measure(candidate)

    assert set(result.scores) == set(FRONTIER_AXES)
    assert result.scores["quality"] == pytest.approx(2 / 3)
    assert result.scores["cost_dollar"] == pytest.approx(candidate.budget.usd)
    assert result.scores["wall_clock_sec"] > 0
    assert result.ladder_id == "tb2"
    assert adapter.ladder_class is LadderClass.STATIC
    assert result.base_model == candidate.base_model
    # Missing per-task costs → declared budget is not measured spend.
    assert result.cost_is_measured is False

    # Equal split: 3.0 min * 60 / 3 tasks = 60 s each.
    assert len(harbor.calls) == 3
    for _task_id, agent_cmd, timeout_sec in harbor.calls:
        assert agent_cmd == candidate.entrypoint
        assert timeout_sec == pytest.approx(60.0)

    summary = Path(result.receipt.artifacts[0])
    assert summary.is_file()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert len(payload["tasks"]) == 3
    by_id = {t["task_id"]: t for t in payload["tasks"]}
    assert by_id["a"]["passed"] is True
    assert by_id["b"]["passed"] is True
    assert by_id["c"]["passed"] is False
    assert payload["timing"]["division"] == "equal_split"
    assert payload["cost_is_measured"] is False


def test_budget_kill_counted_failed_still_returns(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, wall_clock_min=3.0)
    candidate = load_candidate(root)
    harbor = _FakeHarbor(
        tasks=["ok", "slow", "ok2"],
        outcomes={
            "ok": HarborTaskResult(passed=True, log_path="/tmp/ok.log"),
            "slow": HarborTaskResult(
                passed=False,
                log_path="/tmp/slow.log",
                timed_out=True,
            ),
            "ok2": HarborTaskResult(passed=True, log_path="/tmp/ok2.log"),
        },
    )
    adapter = Tb2HarborAdapter(harbor)

    result = adapter.measure(candidate)

    # Timed-out task counted failed; MeasureResult still returned.
    assert result.scores["quality"] == pytest.approx(2 / 3)
    assert result.scores["wall_clock_sec"] > 0
    summary = json.loads(Path(result.receipt.artifacts[0]).read_text(encoding="utf-8"))
    slow = next(t for t in summary["tasks"] if t["task_id"] == "slow")
    assert slow["passed"] is False
    assert slow["timed_out"] is True


def test_receipt_always_self_reported_with_existing_artifacts(
    tmp_path: Path,
) -> None:
    root = _write_candidate(tmp_path)
    candidate = load_candidate(root)
    # Materialize fake log files so artifact existence checks are real.
    log_a = tmp_path / "harbor-a.log"
    log_b = tmp_path / "harbor-b.log"
    log_a.write_text("ok\n", encoding="utf-8")
    log_b.write_text("fail\n", encoding="utf-8")
    harbor = _FakeHarbor(
        tasks=["a", "b"],
        outcomes={
            "a": HarborTaskResult(passed=True, log_path=str(log_a)),
            "b": HarborTaskResult(passed=False, log_path=str(log_b)),
        },
    )
    adapter = Tb2HarborAdapter(harbor)

    result = adapter.measure(candidate)

    assert result.receipt.tier == "self_reported"
    assert result.receipt.kind == "raw_artifacts"
    assert len(result.receipt.artifacts) >= 2
    for artifact in result.receipt.artifacts:
        assert Path(artifact).is_file()
    summary = Path(result.receipt.artifacts[0])
    assert summary.is_relative_to(root / ".adx" / "runs") or str(summary).startswith(
        str((root / ".adx" / "runs").resolve())
    )


def test_pre_run_check_rejects_candidate_without_tb2(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, ladders=["arc-agi-3"])
    candidate = load_candidate(root)
    adapter = Tb2HarborAdapter(_FakeHarbor())

    with pytest.raises(ValueError, match="not in candidate.ladders"):
        adapter.measure(candidate)


def test_measured_cost_when_protocol_reports_it(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, usd=9.99)
    candidate = load_candidate(root)
    harbor = _FakeHarbor(
        tasks=["a", "b"],
        outcomes={
            "a": HarborTaskResult(passed=True, log_path="/tmp/a.log", cost_dollar=0.4),
            "b": HarborTaskResult(passed=True, log_path="/tmp/b.log", cost_dollar=0.6),
        },
    )
    adapter = Tb2HarborAdapter(harbor)

    result = adapter.measure(candidate)

    assert result.scores["cost_dollar"] == pytest.approx(1.0)
    assert result.cost_is_measured is True
    payload = json.loads(Path(result.receipt.artifacts[0]).read_text(encoding="utf-8"))
    assert payload["cost_is_measured"] is True
    assert payload["scores"]["cost_dollar"] == pytest.approx(1.0)


def test_partial_task_costs_fall_back_unmeasured(tmp_path: Path) -> None:
    """Any missing HarborTaskResult.cost_dollar → budget fallback, not measured."""
    root = _write_candidate(tmp_path, usd=4.5)
    candidate = load_candidate(root)
    harbor = _FakeHarbor(
        tasks=["a", "b"],
        outcomes={
            "a": HarborTaskResult(passed=True, log_path="/tmp/a.log", cost_dollar=0.4),
            "b": HarborTaskResult(passed=True, log_path="/tmp/b.log"),  # missing
        },
    )
    adapter = Tb2HarborAdapter(harbor)

    result = adapter.measure(candidate)

    assert result.scores["cost_dollar"] == pytest.approx(candidate.budget.usd)
    assert result.cost_is_measured is False


def test_cost_dollar_override_is_measured(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, usd=9.99)
    candidate = load_candidate(root)
    harbor = _FakeHarbor(
        tasks=["a"],
        outcomes={"a": HarborTaskResult(passed=True, log_path="/tmp/a.log")},
    )
    adapter = Tb2HarborAdapter(harbor, cost_dollar=0.77)

    result = adapter.measure(candidate)

    assert result.scores["cost_dollar"] == pytest.approx(0.77)
    assert result.cost_is_measured is True
    payload = json.loads(Path(result.receipt.artifacts[0]).read_text(encoding="utf-8"))
    assert payload["cost_is_measured"] is True
