"""Tests for ``adx measure`` (M2 WU-5)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml
from adx_frontier.candidate import FRONTIER_AXES
from agentdex_cli.cli import main

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


def _write_candidate(
    tmp_path: Path,
    *,
    ladders: list[str] | None = None,
    files: dict[str, bytes] | None = None,
    entrypoint: str | None = None,
    echo_agent: bool = False,
) -> Path:
    if files is None:
        files = {"src/noop.py": b"# noop\n"}
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    if echo_agent:
        script = tmp_path / "agent.py"
        script.write_text(_ECHO_AGENT, encoding="utf-8")
        entrypoint = f"{sys.executable} agent.py"
    elif entrypoint is None:
        agent = tmp_path / "agent.py"
        agent.write_text("print('ok')\n", encoding="utf-8")
        entrypoint = f"{sys.executable} agent.py"

    manifest = {
        "name": "measure-test-agent",
        "entrypoint": entrypoint,
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": 5.0, "wall_clock_min": 5.0},
        "ladders": ladders if ladders is not None else ["arc-agi-3", "tb2"],
    }
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def test_gate_rejection_oversized_mutable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {f"src/f{i}.py": b"x\n" for i in range(11)}
    root = _write_candidate(tmp_path, files=files)

    rc = main(["measure", "--agent", str(root), "--ladder", "tb2", "--engine-fake"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "narrow your weco-mutable subset" in err


def test_happy_path_tb2_engine_fake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])
    out_path = tmp_path / "out.json"

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine-fake",
            "--out",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert set(payload["scores"]) == set(FRONTIER_AXES)
    assert payload["receipt"]["kind"] == "fake_engine"
    assert payload["receipt"]["tier"] == "self_reported"
    assert payload["ladder_id"] == "tb2"
    assert payload["base_model"] == "claude-sonnet-5"
    assert "usd" in payload["budget"] and "wall_clock_min" in payload["budget"]
    assert "measured_at_utc" in payload
    # FakeHarbor reports per-task cost_dollar → measured honesty bit is True.
    assert payload["cost_is_measured"] is True
    assert out_path.is_file()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload


def test_happy_path_arc_agi3_engine_fake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _write_candidate(
        tmp_path,
        ladders=["arc-agi-3", "tb2"],
        echo_agent=True,
    )

    rc = main(["measure", "--agent", str(root), "--ladder", "arc-agi-3", "--engine-fake"])

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert set(payload["scores"]) == set(FRONTIER_AXES)
    assert payload["receipt"]["kind"] == "fake_engine"
    assert payload["receipt"]["tier"] == "self_reported"
    assert payload["ladder_id"] == "arc-agi-3"
    assert payload["scores"]["quality"] == pytest.approx(0.42)
    # FakeArcEngine has no measured cost → budget fallback is not measured.
    assert payload["cost_is_measured"] is False


def test_unknown_ladder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path)

    rc = main(["measure", "--agent", str(root), "--ladder", "not-a-ladder", "--engine-fake"])

    err = capsys.readouterr().err
    assert rc != 0
    assert "unknown ladder" in err


def test_run_adapter_false_kaggle_exits_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # kaggle is in KNOWN_LADDERS but run_adapter:false in the registry.
    root = _write_candidate(tmp_path, ladders=["kaggle", "tb2"])

    rc = main(["measure", "--agent", str(root), "--ladder", "kaggle", "--engine-fake"])

    err = capsys.readouterr().err
    assert rc == 3
    assert "run_adapter=false" in err or "run_adapter" in err


def test_nan_budget_exits_gate_without_nan_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1-1: NaN budget → exit 2, no NaN token in stdout/stderr."""
    root = _write_candidate(tmp_path)
    # Overwrite budget with YAML .nan (float NaN after load).
    manifest = yaml.safe_load((root / "candidate.yaml").read_text(encoding="utf-8"))
    manifest["budget"] = {"usd": float("nan"), "wall_clock_min": float("nan")}
    (root / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    rc = main(["measure", "--agent", str(root), "--ladder", "tb2", "--engine-fake"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc == 2
    assert "NaN" not in combined
    assert "finite" in captured.err or "budget" in captured.err


def test_absolute_mutable_glob_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """P2-b: absolute mutable glob → clean exit 2, not a traceback."""
    outside = tmp_path / "outside.py"
    outside.write_text("x\n", encoding="utf-8")
    root = _write_candidate(tmp_path / "agent")
    manifest = yaml.safe_load((root / "candidate.yaml").read_text(encoding="utf-8"))
    manifest["mutable"] = [str(outside.resolve())]
    (root / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    rc = main(["measure", "--agent", str(root), "--ladder", "tb2", "--engine-fake"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in captured.err
    assert "absolute" in captured.err or "mutable" in captured.err


_GREEDY_AGENT = textwrap.dedent(
    """\
    import json
    import sys

    def choose(frame):
        agent = frame.get("agent") or [0, 0]
        goal = frame.get("goal") or [0, 0]
        ar, ac = int(agent[0]), int(agent[1])
        gr, gc = int(goal[0]), int(goal[1])
        if ar < gr:
            return "down"
        if ar > gr:
            return "up"
        if ac < gc:
            return "right"
        if ac > gc:
            return "left"
        return "up"

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("type") == "observation":
            action = choose(msg.get("frame") or {})
            print(json.dumps({"type": "action", "action": action}), flush=True)
    """
)


def test_happy_path_arc_local_engine(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """WU-7: --engine local-arc produces a genuine measured self_reported run."""
    root = tmp_path / "arc-scripted"
    root.mkdir()
    (root / "agent.py").write_text(_GREEDY_AGENT, encoding="utf-8")
    manifest = {
        "name": "arc-scripted-heuristic",
        "entrypoint": f"{sys.executable} agent.py",
        "mutable": ["agent.py"],
        "base_model": "scripted-heuristic-no-llm",
        "budget": {"usd": 1.0, "wall_clock_min": 2.0},
        "ladders": ["arc-agi-3"],
    }
    (root / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "arc-agi-3",
            "--engine",
            "local-arc",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert set(payload["scores"]) == set(FRONTIER_AXES)
    assert payload["cost_is_measured"] is True
    assert payload["scores"]["cost_dollar"] == 0.0
    assert payload["receipt"]["tier"] == "self_reported"
    assert payload["receipt"]["kind"] != "fake_engine"
    quality = payload["scores"]["quality"]
    assert isinstance(quality, (int, float))
    assert 0.0 <= float(quality) <= 1.0
    assert payload["ladder_id"] == "arc-agi-3"


def test_local_arc_engine_rejects_non_arc_ladder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WU-7: --engine local-arc on tb2 exits _EXIT_NO_ADAPTER cleanly."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(["measure", "--agent", str(root), "--ladder", "tb2", "--engine", "local-arc"])

    captured = capsys.readouterr()
    assert rc == 3
    assert "local-arc" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_cli_engine_rejects_non_tb2_ladder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WU-8: --engine harbor-cli on arc-agi-3 exits _EXIT_NO_ADAPTER cleanly."""
    root = _write_candidate(tmp_path, ladders=["arc-agi-3", "tb2"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "arc-agi-3",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "harbor-cli" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_cli_missing_binary_clean_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WU-8: missing harbor binary → exit 3, actionable message, no traceback."""
    # Empty PATH so shutil.which("harbor") fails during HarborCliClient init.
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "empty-bin").mkdir()
    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "uv tool install harbor" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_cli_missing_tasks_exits_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2 #10 / WU-12: --engine harbor-cli without --harbor-tasks → exit 2."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "harbor"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--harbor-tasks" in captured.err
    assert "requires" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_engine_fake_conflicts_with_explicit_real_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P3 #11 / WU-12: --engine-fake + --engine harbor-cli → exit 2, no silent override."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine-fake",
            "--engine",
            "harbor-cli",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "conflict" in captured.err.lower() or "conflicts" in captured.err.lower()
    assert "harbor-cli" in captured.err
    assert "Traceback" not in captured.err


def test_engine_fake_with_engine_fake_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P3 #11 / WU-12: --engine-fake --engine fake is same-intent and allowed."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine-fake",
            "--engine",
            "fake",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert payload["receipt"]["kind"] == "fake_engine"


def test_jobs_dir_durable_artifacts_under_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2 #3 / P3 #7 / WU-12: --jobs-dir lands harbor artifacts + receipt under it."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_harbor_for_measure(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])
    jobs_dir = tmp_path / "durable-jobs"

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world",
            "--jobs-dir",
            str(jobs_dir),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert jobs_dir.is_dir()
    artifacts = payload["receipt"]["artifacts"]
    assert artifacts, "expected at least one receipt artifact"
    jobs_resolved = jobs_dir.resolve()
    under_jobs = [
        art
        for art in artifacts
        if jobs_resolved in Path(art).resolve().parents or Path(art).resolve() == jobs_resolved
    ]
    assert under_jobs, (
        f"expected at least one receipt artifact under jobs-dir {jobs_dir!r}; "
        f"got artifacts={artifacts!r}"
    )
    # Stub also writes .argv-*.json under jobs_dir — prove the durable land.
    argv_files = list(jobs_dir.glob(".argv-*.json"))
    assert argv_files, f"expected stub argv files under {jobs_dir}"


def test_jobs_dir_rejects_non_harbor_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """P2 #3 / WU-12: --jobs-dir with --engine local-arc → exit 2."""
    root = _write_candidate(tmp_path, ladders=["arc-agi-3", "tb2"], echo_agent=True)

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "arc-agi-3",
            "--engine",
            "local-arc",
            "--jobs-dir",
            str(tmp_path / "jobs"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--jobs-dir" in captured.err
    assert "harbor-cli" in captured.err
    assert "Traceback" not in captured.err


def test_jobs_dir_existing_file_exits_gate_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WU-12F: --jobs-dir pointing at an existing regular file → exit 2, no traceback."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_harbor_for_measure(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])
    bad_jobs = tmp_path / "not-a-dir"
    bad_jobs.write_text("regular file\n", encoding="utf-8")

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world",
            "--jobs-dir",
            str(bad_jobs),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--jobs-dir" in captured.err
    assert "not a usable directory" in captured.err
    assert "Traceback" not in captured.err


def test_jobs_dir_nested_under_file_exits_gate_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WU-12F: --jobs-dir nested under a file (NotADirectoryError) → exit 2, no traceback."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_harbor_for_measure(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])
    file_parent = tmp_path / "file-as-parent"
    file_parent.write_text("regular file\n", encoding="utf-8")
    nested_jobs = file_parent / "nested" / "jobs"

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world",
            "--jobs-dir",
            str(nested_jobs),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--jobs-dir" in captured.err
    assert "not a usable directory" in captured.err
    assert "Traceback" not in captured.err


def _write_stub_harbor_for_measure(bin_dir: Path) -> Path:
    """Minimal stub harbor that writes TrialResult under -o/--job-name."""
    script = bin_dir / "harbor"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, sys
            from pathlib import Path

            def _arg(flag_long, flag_short=None, default=None):
                argv = sys.argv[1:]
                for i, a in enumerate(argv):
                    if a == flag_long or (flag_short and a == flag_short):
                        if i + 1 < len(argv):
                            return argv[i + 1]
                    if a.startswith(flag_long + "="):
                        return a.split("=", 1)[1]
                return default

            if len(sys.argv) < 2 or sys.argv[1] != "run":
                raise SystemExit(2)
            task_id = _arg("--include-task-name", "-i")
            jobs_dir = Path(_arg("--jobs-dir", "-o", "jobs"))
            job_name = _arg("--job-name", default="stub-job")
            agent = _arg("--agent", "-a", default="")
            jobs_dir.mkdir(parents=True, exist_ok=True)
            (jobs_dir / f".argv-{{job_name}}.json").write_text(
                json.dumps({{"argv": sys.argv, "agent": agent, "task_id": task_id}})
                + "\\n",
                encoding="utf-8",
            )
            trial_dir = jobs_dir / job_name / f"trial-{{task_id}}"
            trial_dir.mkdir(parents=True, exist_ok=True)
            result = {{
                "task_name": task_id,
                "trial_name": f"trial-{{task_id}}",
                "verifier_result": {{"rewards": {{"reward": 0.0}}}},
                "agent_result": {{"cost_usd": 0.0}},
            }}
            (trial_dir / "result.json").write_text(
                json.dumps(result, indent=2) + "\\n", encoding="utf-8"
            )
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_harbor_tasks_forwarded_end_to_end(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WU-9: --harbor-tasks reaches HarborCliClient and is used as -i."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_harbor_for_measure(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])
    out_path = tmp_path / "out.json"

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "hello-world,other-task",
            "--out",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert payload["ladder_id"] == "tb2"
    assert payload["scores"]["quality"] == pytest.approx(0.0)
    assert payload["receipt"]["kind"] == "raw_artifacts"
    assert out_path.is_file()

    # Stub wrote .argv-*.json into HarborCliClient.jobs_dir; log_path artifacts
    # are trial dirs under that jobs_dir (…/job-name/trial-<task>).
    argv_task_ids: set[str] = set()
    for art in payload["receipt"]["artifacts"]:
        art_path = Path(art)
        if not art_path.exists():
            continue
        # Walk parents looking for the jobs_dir that holds .argv-*.json.
        for parent in [art_path, *art_path.parents]:
            for argv_file in parent.glob(".argv-*.json"):
                data = json.loads(argv_file.read_text(encoding="utf-8"))
                tid = data.get("task_id")
                if isinstance(tid, str) and tid:
                    argv_task_ids.add(tid)
    assert argv_task_ids == {"hello-world", "other-task"}, (
        f"expected both tasks forwarded via -i; got {argv_task_ids!r}; "
        f"artifacts={payload['receipt']['artifacts']!r}"
    )


def test_harbor_tasks_rejects_empty_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WU-9: empty/whitespace --harbor-tasks items → exit 2, clean stderr."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "ok,,bad",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--harbor-tasks" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_tasks_rejects_whitespace_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WU-9: whitespace-only task name → exit 2."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "  ",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--harbor-tasks" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_tasks_rejects_non_harbor_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WU-9: --harbor-tasks with --engine-fake → exit 2."""
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine-fake",
            "--harbor-tasks",
            "hello-world",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "--harbor-tasks" in captured.err
    assert "harbor-cli" in captured.err
    assert "Traceback" not in captured.err


def test_harbor_tasks_org_prefix_passed_verbatim(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WU-9F: org/name task ids pass through verbatim (no glob rewrite)."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_harbor_for_measure(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = _write_candidate(tmp_path / "agent", ladders=["tb2", "arc-agi-3"])

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine",
            "harbor-cli",
            "--harbor-tasks",
            "terminal-bench/regex-log",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)

    argv_task_ids: set[str] = set()
    for art in payload["receipt"]["artifacts"]:
        art_path = Path(art)
        if not art_path.exists():
            continue
        for parent in [art_path, *art_path.parents]:
            for argv_file in parent.glob(".argv-*.json"):
                data = json.loads(argv_file.read_text(encoding="utf-8"))
                tid = data.get("task_id")
                if isinstance(tid, str) and tid:
                    argv_task_ids.add(tid)
    # Verbatim pass-through — HarborCliClient slugs only on-disk job/log names.
    assert argv_task_ids == {"terminal-bench/regex-log"}, argv_task_ids
