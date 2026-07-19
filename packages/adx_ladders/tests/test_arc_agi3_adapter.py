"""Unit tests for ArcAgi3Adapter — fakes only, no network."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from adx_frontier.candidate import FRONTIER_AXES, load_candidate
from adx_ladders.adapters.arc_agi3 import ArcAgi3Adapter
from adx_ladders.base import LadderClass


class _FakeEngine:
    """In-memory ARC engine stub for unit tests."""

    def __init__(
        self,
        *,
        quality: float = 0.75,
        scorecard: str | None = None,
        steps_to_done: int = 1,
    ) -> None:
        self._quality = quality
        self._scorecard = scorecard
        self._steps_to_done = steps_to_done
        self._step = 0
        self._game: str | None = None

    def reset(self, game_id: str) -> dict[str, Any]:
        self._game = game_id
        self._step = 0
        return {"frame": {"grid": [[0]], "game": game_id}, "done": False}

    def step(self, action: Any) -> dict[str, Any]:
        self._step += 1
        done = self._step >= self._steps_to_done
        return {
            "frame": {"grid": [[1]], "last_action": action, "game": self._game},
            "done": done,
        }

    def score(self) -> float:
        return self._quality

    def scorecard_id(self) -> str | None:
        return self._scorecard


_ECHO_AGENT = textwrap.dedent(
    """\
    import json
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("type") == "observation":
            print(json.dumps({"type": "action", "action": "idle"}), flush=True)
    """
)

_SLEEP_AGENT = textwrap.dedent(
    """\
    import time
    time.sleep(30)
    """
)

_GRANDCHILD_AGENT = textwrap.dedent(
    """\
    import subprocess
    import sys
    import time
    from pathlib import Path

    pid_path = Path("grandchild.pid")
    gc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    pid_path.write_text(str(gc.pid), encoding="utf-8")
    time.sleep(60)
    """
)


def _write_candidate(
    tmp_path: Path,
    *,
    entrypoint_script: str,
    script_name: str = "agent.py",
    ladders: list[str] | None = None,
    wall_clock_min: float = 5.0,
    usd: float = 1.0,
) -> Path:
    script = tmp_path / script_name
    script.write_text(entrypoint_script, encoding="utf-8")
    # Touch a tiny mutable file so validate() expands cleanly.
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "noop.py").write_text("# noop\n", encoding="utf-8")

    manifest = {
        "name": "arc-fake-agent",
        "entrypoint": f"{sys.executable} {script_name}",
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": usd, "wall_clock_min": wall_clock_min},
        "ladders": ladders if ladders is not None else ["arc-agi-3", "tb2"],
    }
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def test_measure_returns_measure_result_with_exact_axes(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT)
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(_FakeEngine(quality=0.8), game_ids=["g0"])

    result = adapter.measure(candidate)

    assert set(result.scores) == set(FRONTIER_AXES)
    assert result.scores["quality"] == pytest.approx(0.8)
    assert result.scores["wall_clock_sec"] > 0
    assert result.ladder_id == "arc-agi-3"
    assert adapter.ladder_class is LadderClass.LIVE_ADVERSARIAL
    assert result.base_model == candidate.base_model
    assert result.budget_usd == candidate.budget.usd
    # No engine/client measured cost → declared budget is not honest spend.
    assert result.cost_is_measured is False
    assert result.scores["cost_dollar"] == pytest.approx(candidate.budget.usd)


def test_budget_fallback_writes_cost_is_measured_false_in_artifact(
    tmp_path: Path,
) -> None:
    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT, usd=3.25)
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(_FakeEngine(quality=0.5, scorecard=None), game_ids=["g0"])

    result = adapter.measure(candidate)

    assert result.cost_is_measured is False
    artifact = Path(result.receipt.artifacts[0])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["cost_is_measured"] is False
    assert payload["scores"]["cost_dollar"] == pytest.approx(3.25)


def test_cost_dollar_override_is_measured(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT, usd=9.99)
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(
        _FakeEngine(quality=0.8),
        game_ids=["g0"],
        cost_dollar=1.23,
    )

    result = adapter.measure(candidate)

    assert result.cost_is_measured is True
    assert result.scores["cost_dollar"] == pytest.approx(1.23)
    artifact = Path(result.receipt.artifacts[0])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["cost_is_measured"] is True
    assert payload["scores"]["cost_dollar"] == pytest.approx(1.23)


def test_verified_receipt_when_scorecard_id_present(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT)
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(
        _FakeEngine(quality=0.9, scorecard="sc-abc-123"),
        game_ids=["g0"],
    )

    result = adapter.measure(candidate)

    assert result.receipt.tier == "verified"
    assert result.receipt.kind == "arc_scorecard_id"
    assert result.receipt.ref == "sc-abc-123"


def test_self_reported_receipt_writes_artifact_file(tmp_path: Path) -> None:
    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT)
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(
        _FakeEngine(quality=0.5, scorecard=None),
        game_ids=["g0"],
    )

    result = adapter.measure(candidate)

    assert result.receipt.tier == "self_reported"
    assert result.receipt.kind == "raw_artifacts"
    assert len(result.receipt.artifacts) == 1
    artifact = Path(result.receipt.artifacts[0])
    assert artifact.is_file()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert "episodes" in payload
    assert "actions_total" in payload
    assert "scores" in payload
    assert "timing" in payload
    assert artifact.is_relative_to(root / ".adx" / "runs") or str(artifact).startswith(
        str((root / ".adx" / "runs").resolve())
    )


def test_budget_kill_reports_quality_zero(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        entrypoint_script=_SLEEP_AGENT,
        wall_clock_min=0.02 / 60.0,  # ~0.02 seconds
    )
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(
        _FakeEngine(quality=0.99, scorecard="should-not-verify-on-timeout"),
        game_ids=["g0"],
    )

    result = adapter.measure(candidate)

    assert result.scores["quality"] == 0.0
    assert result.scores["wall_clock_sec"] > 0
    # Timeout forces honest self-reported artifacts even if engine has an id.
    assert result.receipt.tier == "self_reported"
    assert Path(result.receipt.artifacts[0]).is_file()


def test_pre_run_check_rejects_candidate_without_arc_ladder(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        entrypoint_script=_ECHO_AGENT,
        ladders=["tb2"],
    )
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(_FakeEngine(), game_ids=["g0"])

    with pytest.raises(ValueError, match="not in candidate.ladders"):
        adapter.measure(candidate)


def test_stdin_write_deadlock_times_out(tmp_path: Path) -> None:
    """P1-2: large frame + non-reading sleeper must not hang past budget."""

    class _HugeFrameEngine(_FakeEngine):
        def reset(self, game_id: str) -> dict[str, Any]:
            self._game = game_id
            self._step = 0
            # Larger than typical OS pipe buffer (~64KiB) so write can block.
            return {
                "frame": {"blob": "x" * 200_000, "game": game_id},
                "done": False,
            }

    root = _write_candidate(
        tmp_path,
        entrypoint_script=_SLEEP_AGENT,
        wall_clock_min=0.15 / 60.0,  # ~0.15 s
    )
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(_HugeFrameEngine(quality=0.99), game_ids=["g0"])

    t0 = time.monotonic()
    result = adapter.measure(candidate)
    elapsed = time.monotonic() - t0

    assert result.scores["quality"] == 0.0
    assert result.receipt.tier == "self_reported"
    # Must finish well under the old hung-for-8s+ failure mode.
    assert elapsed < 3.0


def test_budget_kill_terminates_grandchild(tmp_path: Path) -> None:
    """P1-3: process-group kill must reap candidate-spawned grandchildren."""
    import os

    root = _write_candidate(
        tmp_path,
        entrypoint_script=_GRANDCHILD_AGENT,
        wall_clock_min=0.25 / 60.0,  # ~0.25 s — enough to fork+record pid
    )
    candidate = load_candidate(root)
    adapter = ArcAgi3Adapter(_FakeEngine(quality=0.99), game_ids=["g0"])

    result = adapter.measure(candidate)
    assert result.scores["quality"] == 0.0

    pid_path = root / "grandchild.pid"
    # The sleeper may be killed before writing the pid; if written, it must die.
    if pid_path.is_file():
        gc_pid = int(pid_path.read_text(encoding="utf-8").strip())
        # Give the kernel a moment after killpg.
        deadline = time.monotonic() + 2.0
        alive = True
        while time.monotonic() < deadline:
            try:
                os.kill(gc_pid, 0)
            except ProcessLookupError:
                alive = False
                break
            except PermissionError:
                # Pid reused by another uid — treat as gone for our purposes.
                alive = False
                break
            time.sleep(0.05)
        assert alive is False, f"grandchild pid {gc_pid} still alive after budget kill"
    else:
        # If pid file never appeared, the group kill still prevented a hang.
        assert result.scores["wall_clock_sec"] < 5.0


def test_readonly_candidate_dir_returns_measure_result(tmp_path: Path) -> None:
    """P2-a: read-only candidate root must not crash measure()."""
    import os
    import stat

    root = _write_candidate(tmp_path, entrypoint_script=_ECHO_AGENT)
    candidate = load_candidate(root)

    def _chmod_tree(path: Path, dir_mode: int, file_mode: int) -> None:
        for dirpath, _dirnames, filenames in os.walk(path, topdown=False):
            for name in filenames:
                os.chmod(Path(dirpath) / name, file_mode)
            os.chmod(dirpath, dir_mode)

    _chmod_tree(root, stat.S_IRUSR | stat.S_IXUSR, stat.S_IRUSR)
    try:
        adapter = ArcAgi3Adapter(_FakeEngine(quality=0.5), game_ids=["g0"])
        result = adapter.measure(candidate)
        assert set(result.scores) == set(FRONTIER_AXES)
        assert result.receipt.tier in ("verified", "self_reported")
        assert result.scores["quality"] == pytest.approx(0.5)
    finally:
        _chmod_tree(root, stat.S_IRWXU, stat.S_IRUSR | stat.S_IWUSR)
