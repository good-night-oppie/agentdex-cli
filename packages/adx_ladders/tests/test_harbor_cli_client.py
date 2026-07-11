"""Hermetic tests for HarborCliClient — stub harbor on PATH, no network/Docker."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml
from adx_frontier.candidate import FRONTIER_AXES, load_candidate
from adx_ladders.adapters.tb2_harbor import Tb2HarborAdapter
from adx_ladders.engines.harbor_cli import HarborCliClient


def _write_stub_harbor(
    bin_dir: Path,
    *,
    outcomes: dict[str, dict[str, object]] | None = None,
    sleep_sec: float = 0.0,
    spawn_grandchild: bool = False,
    chatty_stdout_bytes: int = 0,
) -> Path:
    """Install a fake ``harbor`` executable that mirrors real CLI flags.

    Parses ``run -d … -i <task> -o <jobs_dir> --job-name <name> -a …`` and
    writes ``<jobs_dir>/<job-name>/<trial>/result.json`` in the real Harbor
    on-disk shape. Optional sleep + grandchild for timeout/kill probes.
    Records full argv to ``<jobs_dir>/.argv-<job-name>.json`` for flag
    assertions. ``chatty_stdout_bytes`` floods stdout before writing results
    (pipe-deadlock regression).
    """
    outcomes = outcomes or {}
    script = bin_dir / "harbor"
    # Encode outcomes as JSON embedded in the stub for hermetic replay.
    outcomes_json = json.dumps(outcomes)
    body = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json, os, signal, sys, time
        from pathlib import Path

        OUTCOMES = json.loads({outcomes_json!r})
        SLEEP_SEC = {sleep_sec!r}
        SPAWN_GC = {spawn_grandchild!r}
        CHATTY_BYTES = {chatty_stdout_bytes!r}

        def _arg(flag_long, flag_short=None, default=None):
            argv = sys.argv[1:]
            for i, a in enumerate(argv):
                if a == flag_long or (flag_short and a == flag_short):
                    if i + 1 < len(argv):
                        return argv[i + 1]
                if a.startswith(flag_long + "="):
                    return a.split("=", 1)[1]
            return default

        if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
            print("Usage: harbor [OPTIONS] COMMAND")
            raise SystemExit(0)
        if sys.argv[1] != "run":
            print("stub only implements: harbor run", file=sys.stderr)
            raise SystemExit(2)

        task_id = _arg("--include-task-name", "-i")
        jobs_dir = Path(_arg("--jobs-dir", "-o", "jobs"))
        job_name = _arg("--job-name", default="stub-job")
        if not task_id:
            print("missing -i/--include-task-name", file=sys.stderr)
            raise SystemExit(2)

        jobs_dir.mkdir(parents=True, exist_ok=True)
        (jobs_dir / f".argv-{{job_name}}.json").write_text(
            json.dumps(sys.argv) + "\\n", encoding="utf-8"
        )

        gc_pid_file = jobs_dir / f".gc-{{job_name}}.pid"
        if SPAWN_GC:
            # Grandchild that ignores SIGTERM — killpg SIGKILL must reap it.
            pid = os.fork()
            if pid == 0:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep(60)
                os._exit(0)
            gc_pid_file.write_text(str(pid), encoding="utf-8")

        if SLEEP_SEC > 0:
            time.sleep(SLEEP_SEC)

        # Flood stdout before writing artifacts — must not deadlock parent.
        if CHATTY_BYTES > 0:
            chunk = b"x" * 4096
            remaining = CHATTY_BYTES
            while remaining > 0:
                n = min(remaining, len(chunk))
                sys.stdout.buffer.write(chunk[:n])
                remaining -= n
            sys.stdout.buffer.flush()

        outcome = OUTCOMES.get(task_id, {{"passed": True}})
        passed = bool(outcome.get("passed", True))
        cost = outcome.get("cost_usd", None)

        # Real Harbor trial dirs are slash-free (e.g. regex-log__N2roHLD);
        # slug task_id so org-prefixed ids stay depth-1 under the job root.
        trial_slug = "".join(
            c if (c.isalnum() or c in "._-") else "_" for c in task_id
        )
        trial_dir = jobs_dir / job_name / f"trial-{{trial_slug}}"
        trial_dir.mkdir(parents=True, exist_ok=True)
        (jobs_dir / job_name / "config.json").write_text("{{}}\\n", encoding="utf-8")
        result = {{
            "task_name": task_id,
            "trial_name": f"trial-{{trial_slug}}",
            "verifier_result": {{
                "rewards": {{"reward": 1.0 if passed else 0.0}},
            }},
            "agent_result": (
                {{"cost_usd": float(cost)}} if cost is not None else None
            ),
        }}
        (trial_dir / "result.json").write_text(
            json.dumps(result, indent=2) + "\\n", encoding="utf-8"
        )
        (trial_dir / "verifier").mkdir(exist_ok=True)
        (trial_dir / "verifier" / "reward.txt").write_text(
            ("1.0" if passed else "0.0") + "\\n", encoding="utf-8"
        )
        raise SystemExit(0)
        """
    )
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def _write_candidate(tmp_path: Path, *, wall_clock_min: float = 3.0) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "noop.py").write_text("# noop\n", encoding="utf-8")
    agent = tmp_path / "agent.py"
    agent.write_text("print('tb2-agent')\n", encoding="utf-8")
    manifest = {
        "name": "tb2-harbor-cli-agent",
        "entrypoint": f"{sys.executable} agent.py",
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": 2.5, "wall_clock_min": wall_clock_min},
        "ladders": ["tb2", "arc-agi-3"],
    }
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def stub_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


def test_happy_path_fields_and_adapter_quality(tmp_path: Path, stub_path: Path) -> None:
    """2 tasks, 1 pass → HarborTaskResult fields exact; adapter quality=0.5."""
    _write_stub_harbor(
        stub_path,
        outcomes={
            "task-a": {"passed": True, "cost_usd": 0.12},
            "task-b": {"passed": False, "cost_usd": 0.08},
        },
    )
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("task-a", "task-b"),
    )

    r_a = client.run_task("task-a", "oracle", timeout_sec=10.0)
    r_b = client.run_task("task-b", "oracle", timeout_sec=10.0)

    assert r_a.passed is True
    assert r_a.timed_out is False
    assert r_a.cost_dollar == pytest.approx(0.12)
    assert Path(r_a.log_path).is_dir()
    assert (Path(r_a.log_path) / "result.json").is_file()

    assert r_b.passed is False
    assert r_b.timed_out is False
    assert r_b.cost_dollar == pytest.approx(0.08)

    root = _write_candidate(tmp_path / "agent")
    candidate = load_candidate(root)
    # Fresh client for adapter (same stub on PATH).
    adapter_client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-adapter",
        tasks=("task-a", "task-b"),
    )
    # Re-seed outcomes for adapter's own run_task calls.
    result = Tb2HarborAdapter(adapter_client, suite="default").measure(candidate)
    assert set(result.scores) == set(FRONTIER_AXES)
    assert result.scores["quality"] == pytest.approx(0.5)
    assert result.cost_is_measured is True
    assert result.scores["cost_dollar"] == pytest.approx(0.20)


def test_timeout_kills_process_group(tmp_path: Path, stub_path: Path) -> None:
    """Stub sleeps past timeout + grandchild; timed_out + group gone."""
    _write_stub_harbor(
        stub_path,
        sleep_sec=30.0,
        spawn_grandchild=True,
    )
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("slow-task",),
    )

    started = time.monotonic()
    result = client.run_task("slow-task", "oracle", timeout_sec=0.4)
    elapsed = time.monotonic() - started

    assert result.timed_out is True
    assert result.passed is False
    assert result.cost_dollar is None
    assert result.log_path == str(jobs)
    assert elapsed < 5.0  # must not wait out the stub's 30s sleep

    # Grandchild pid file may exist under jobs; if written, process must be dead.
    gc_files = list(jobs.glob(".gc-*.pid"))
    # Race: stub may be killed before writing pid; only assert when present.
    for gf in gc_files:
        gc_pid = int(gf.read_text(encoding="utf-8").strip())
        # Wait briefly for SIGKILL to land.
        dead = False
        for _ in range(20):
            try:
                os.kill(gc_pid, 0)
            except OSError:
                dead = True
                break
            time.sleep(0.05)
        assert dead, f"grandchild pid {gc_pid} still alive after killpg"


def test_timeout_grandchild_reaped_when_pid_written(
    tmp_path: Path, stub_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stronger grandchild probe: short sleep before long sleep so pid is written."""
    # Custom stub: write grandchild pid immediately, then sleep forever.
    bin_dir = stub_path
    script = bin_dir / "harbor"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os, signal, sys, time
            from pathlib import Path

            def _arg(flag_long, flag_short=None, default=None):
                argv = sys.argv[1:]
                for i, a in enumerate(argv):
                    if a == flag_long or (flag_short and a == flag_short):
                        return argv[i + 1] if i + 1 < len(argv) else default
                return default

            if sys.argv[1] != "run":
                raise SystemExit(2)
            jobs_dir = Path(_arg("--jobs-dir", "-o", "jobs"))
            job_name = _arg("--job-name", default="j")
            jobs_dir.mkdir(parents=True, exist_ok=True)
            pid = os.fork()
            if pid == 0:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep(120)
                os._exit(0)
            (jobs_dir / f".gc-{{job_name}}.pid").write_text(str(pid))
            # Flush then sleep past parent timeout.
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)

    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("t",),
    )
    result = client.run_task("t", "oracle", timeout_sec=0.5)
    assert result.timed_out is True
    assert result.passed is False

    gc_files = list(jobs.glob(".gc-*.pid"))
    assert gc_files, "grandchild pid file should exist"
    gc_pid = int(gc_files[0].read_text(encoding="utf-8").strip())
    dead = False
    for _ in range(40):
        try:
            os.kill(gc_pid, 0)
        except OSError:
            dead = True
            break
        time.sleep(0.05)
    assert dead, f"grandchild {gc_pid} leaked after process-group kill"


def test_cost_propagated_or_none(tmp_path: Path, stub_path: Path) -> None:
    """With cost_usd → cost_dollar set; without → None → cost_is_measured=False."""
    _write_stub_harbor(
        stub_path,
        outcomes={
            "with-cost": {"passed": True, "cost_usd": 1.25},
            "no-cost": {"passed": True},  # cost_usd omitted
        },
    )
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs",
        tasks=("with-cost", "no-cost"),
    )
    with_cost = client.run_task("with-cost", "oracle", timeout_sec=5.0)
    no_cost = client.run_task("no-cost", "oracle", timeout_sec=5.0)
    assert with_cost.cost_dollar == pytest.approx(1.25)
    assert no_cost.cost_dollar is None

    root = _write_candidate(tmp_path / "agent", wall_clock_min=2.0)
    candidate = load_candidate(root)
    # Suite of one no-cost task → adapter falls back to budget.usd.
    adapter_client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs2",
        tasks=("no-cost",),
    )
    result = Tb2HarborAdapter(adapter_client).measure(candidate)
    assert result.cost_is_measured is False
    assert result.scores["cost_dollar"] == pytest.approx(candidate.budget.usd)


def test_binary_missing_actionable_error(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-harbor-bin"
    with pytest.raises(FileNotFoundError, match="uv tool install harbor"):
        HarborCliClient(
            harbor_bin=str(missing),
            jobs_dir=tmp_path / "jobs",
            tasks=("t0",),
        )


def test_list_tasks_fallback_and_none_raises(tmp_path: Path, stub_path: Path) -> None:
    _write_stub_harbor(stub_path)
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs",
        tasks=("alpha", "beta"),
    )
    assert client.list_tasks("any-suite") == ["alpha", "beta"]

    with pytest.raises(ValueError, match="tasks="):
        HarborCliClient(
            harbor_bin="harbor",
            jobs_dir=tmp_path / "jobs2",
            tasks=None,
        ).list_tasks("default")


def test_f1_chatty_stdout_does_not_pipe_deadlock(tmp_path: Path, stub_path: Path) -> None:
    """F1: chatty child (>128KB stdout) must not deadlock; passed=True."""
    _write_stub_harbor(
        stub_path,
        outcomes={"chatty": {"passed": True, "cost_usd": 0.01}},
        chatty_stdout_bytes=128 * 1024 + 4096,
    )
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("chatty",),
    )
    started = time.monotonic()
    result = client.run_task("chatty", "oracle", timeout_sec=10.0)
    elapsed = time.monotonic() - started

    assert result.passed is True
    assert result.timed_out is False
    assert elapsed < 5.0
    # Diagnostic log retained on disk (merged stdout+stderr redirect).
    logs = list(jobs.glob("*.harbor.log"))
    assert logs, "expected <job_name>.harbor.log diagnostic file"
    assert logs[0].stat().st_size >= 128 * 1024


def test_f2_argv_includes_n_tasks_cap(tmp_path: Path, stub_path: Path) -> None:
    """F2: argv must hard-cap with -l 1 (n-tasks) alongside -n 1 (concurrency)."""
    _write_stub_harbor(stub_path, outcomes={"t0": {"passed": True}})
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("t0",),
    )
    result = client.run_task("t0", "oracle", timeout_sec=5.0)
    assert result.passed is True

    argv_files = list(jobs.glob(".argv-*.json"))
    assert argv_files, "stub should record argv"
    argv = json.loads(argv_files[0].read_text(encoding="utf-8"))
    # -n 1 = concurrency; -l 1 = hard task cap after filters.
    assert "-n" in argv and argv[argv.index("-n") + 1] == "1"
    assert "-l" in argv and argv[argv.index("-l") + 1] == "1"


def test_org_prefixed_task_id_exact_filter_slugged_paths(tmp_path: Path, stub_path: Path) -> None:
    """WU-9F: org/task-x → -i exact; job/log paths slash-free; passed honored."""
    task_id = "org/task-x"
    _write_stub_harbor(
        stub_path,
        outcomes={task_id: {"passed": True, "cost_usd": 0.07}},
    )
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=(task_id,),
    )
    result = client.run_task(task_id, "oracle", timeout_sec=5.0)

    assert result.passed is True
    assert result.timed_out is False
    assert result.cost_dollar == pytest.approx(0.07)
    assert (Path(result.log_path) / "result.json").is_file()

    argv_files = list(jobs.glob(".argv-*.json"))
    assert argv_files, "stub should record argv"
    argv = json.loads(argv_files[0].read_text(encoding="utf-8"))
    assert "-i" in argv and argv[argv.index("-i") + 1] == "org/task-x"

    job_dirs = [p for p in jobs.iterdir() if p.is_dir()]
    assert job_dirs, "expected slugged job directory"
    for jd in job_dirs:
        assert "/" not in jd.name
        assert "org_task-x" in jd.name

    logs = list(jobs.glob("*.harbor.log"))
    assert logs, "expected <job_name>.harbor.log"
    for log in logs:
        assert "/" not in log.name
        assert "org_task-x" in log.name
        assert log.is_file()


def _write_trial_result(
    path: Path,
    *,
    task_name: str,
    reward: float,
    cost_usd: float | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "task_name": task_name,
        "verifier_result": {"rewards": {"reward": reward}},
    }
    if cost_usd is not None:
        payload["agent_result"] = {"cost_usd": cost_usd}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_forged_artifact_result_json_ignored(tmp_path: Path, stub_path: Path) -> None:
    """WU-10 P1: agent-planted artifacts/.../result.json must not gate pass/cost.

    Genuine verifier file at depth-1 has reward=0 + org-prefixed task_name;
    forged file under artifacts/ matches the bare --harbor-tasks id with
    reward=1 + cost_usd=0. Path confinement must honor only the trial root.
    """
    _write_stub_harbor(stub_path)  # binary present for client ctor
    job_dir = tmp_path / "wu9-oracle"
    trial_dir = job_dir / "regex-log__N2roHLD"
    trial_dir.mkdir(parents=True)
    (job_dir / "result.json").write_text("{}\n", encoding="utf-8")  # job-level

    _write_trial_result(
        trial_dir / "result.json",
        task_name="terminal-bench/regex-log",
        reward=0.0,
    )
    _write_trial_result(
        trial_dir / "artifacts" / "logs" / "artifacts" / "result.json",
        task_name="regex-log",
        reward=1.0,
        cost_usd=0.0,
    )

    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-unused",
        tasks=("regex-log",),
    )
    result = client._parse_job_result(job_dir, task_id="regex-log")
    assert result.passed is False
    assert result.cost_dollar is None
    assert result.timed_out is False
    assert result.errored is False  # genuine reward-0, not infra failure
    assert Path(result.log_path) == trial_dir


def test_depth1_trial_result_honors_org_prefixed_task_name(tmp_path: Path, stub_path: Path) -> None:
    """WU-10: single depth-1 trial root is trusted even when task_name is org-prefixed."""
    _write_stub_harbor(stub_path)
    job_dir = tmp_path / "job"
    trial_dir = job_dir / "regex-log__abc"
    _write_trial_result(
        trial_dir / "result.json",
        task_name="terminal-bench/regex-log",
        reward=1.0,
        cost_usd=0.42,
    )

    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-unused",
        tasks=("regex-log",),
    )
    result = client._parse_job_result(job_dir, task_id="regex-log")
    assert result.passed is True
    assert result.cost_dollar == pytest.approx(0.42)
    assert Path(result.log_path) == trial_dir


@pytest.mark.parametrize("requested_task", ["different-task", "*"])
def test_single_trial_result_rejects_wrong_task_identity(
    tmp_path: Path, stub_path: Path, requested_task: str
) -> None:
    """WU-13: a sole result cannot bypass requested-task identity matching."""
    _write_stub_harbor(stub_path)
    job_dir = tmp_path / "job"
    _write_trial_result(
        job_dir / "easier-task__abc" / "result.json",
        task_name="terminal-bench/easier-task",
        reward=1.0,
        cost_usd=0.0,
    )

    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-unused",
        tasks=(requested_task,),
    )
    result = client._parse_job_result(job_dir, task_id=requested_task)
    assert result.errored is True
    assert result.passed is False
    assert result.cost_dollar is None


def test_empty_job_dir_honest_non_measurement(tmp_path: Path, stub_path: Path) -> None:
    """WU-10/WU-11: no trial-root result.json → errored=True (not measured-0)."""
    _write_stub_harbor(stub_path)
    job_dir = tmp_path / "empty-job"
    job_dir.mkdir()
    (job_dir / "result.json").write_text("{}\n", encoding="utf-8")
    (job_dir / "config.json").write_text("{}\n", encoding="utf-8")

    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-unused",
        tasks=("regex-log",),
    )
    result = client._parse_job_result(job_dir, task_id="regex-log")
    assert result.passed is False
    assert result.cost_dollar is None
    assert result.timed_out is False
    assert result.errored is True
    assert result.log_path == str(job_dir)

    missing = tmp_path / "no-such-job"
    result_missing = client._parse_job_result(missing, task_id="regex-log")
    assert result_missing.passed is False
    assert result_missing.cost_dollar is None
    assert result_missing.errored is True


def test_p2_6_non_timeout_exception_reaps_process_group(
    tmp_path: Path, stub_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WU-11 P2 #6: KeyboardInterrupt during wait → _kill runs, exception propagates."""
    _write_stub_harbor(
        stub_path,
        sleep_sec=30.0,
        spawn_grandchild=True,
    )
    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("t",),
    )

    kill_calls: list[object] = []
    real_kill = HarborCliClient._kill

    def _tracking_kill(proc: object) -> None:
        kill_calls.append(proc)
        real_kill(proc)  # type: ignore[arg-type]

    # _kill is a staticmethod — wrap so instance call does not bind self.
    monkeypatch.setattr(HarborCliClient, "_kill", staticmethod(_tracking_kill))

    import subprocess

    real_popen = subprocess.Popen

    class _Popen(real_popen):  # type: ignore[valid-type,misc]
        def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
            raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "Popen", _Popen)

    with pytest.raises(KeyboardInterrupt):
        client.run_task("t", "oracle", timeout_sec=10.0)

    assert kill_calls, "_kill must run on non-timeout wait exception"


def test_p2_9_infra_fail_nonzero_exit_no_trial_result(tmp_path: Path, stub_path: Path) -> None:
    """WU-11 P2 #9: harbor exits nonzero with no trial result → errored, not quality=0."""
    bin_dir = stub_path
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
                        return argv[i + 1] if i + 1 < len(argv) else default
                return default

            if sys.argv[1] != "run":
                raise SystemExit(2)
            jobs_dir = Path(_arg("--jobs-dir", "-o", "jobs"))
            job_name = _arg("--job-name", default="j")
            jobs_dir.mkdir(parents=True, exist_ok=True)
            (jobs_dir / job_name).mkdir(parents=True, exist_ok=True)
            (jobs_dir / f".argv-{{job_name}}.json").write_text(
                json.dumps(sys.argv) + "\\n", encoding="utf-8"
            )
            # Infra failure: nonzero exit, no trial result.json written.
            raise SystemExit(1)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)

    jobs = tmp_path / "jobs"
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=jobs,
        tasks=("broken",),
    )
    harbor_result = client.run_task("broken", "oracle", timeout_sec=5.0)
    assert harbor_result.errored is True
    assert harbor_result.passed is False
    assert harbor_result.timed_out is False
    assert harbor_result.cost_dollar is None

    root = _write_candidate(tmp_path / "agent", wall_clock_min=1.0)
    candidate = load_candidate(root)
    adapter_client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs-adapter",
        tasks=("broken",),
    )
    result = Tb2HarborAdapter(adapter_client).measure(candidate)
    assert result.scores["quality"] == pytest.approx(0.0)
    assert result.cost_is_measured is False
    payload = json.loads(Path(result.receipt.artifacts[0]).read_text(encoding="utf-8"))
    assert payload["errored_count"] >= 1
    assert payload["n_tasks"] == 1
    assert payload["tasks"][0]["errored"] is True
    assert payload["cost_is_measured"] is False


def test_p2_9_clean_run_still_measured(tmp_path: Path, stub_path: Path) -> None:
    """WU-11 regression: clean all-measured run keeps cost_is_measured + errored_count=0."""
    _write_stub_harbor(
        stub_path,
        outcomes={
            "a": {"passed": True, "cost_usd": 0.10},
            "b": {"passed": True, "cost_usd": 0.20},
        },
    )
    root = _write_candidate(tmp_path / "agent", wall_clock_min=2.0)
    candidate = load_candidate(root)
    client = HarborCliClient(
        harbor_bin="harbor",
        jobs_dir=tmp_path / "jobs",
        tasks=("a", "b"),
    )
    result = Tb2HarborAdapter(client).measure(candidate)
    assert result.cost_is_measured is True
    assert result.scores["quality"] == pytest.approx(1.0)
    assert result.scores["cost_dollar"] == pytest.approx(0.30)
    payload = json.loads(Path(result.receipt.artifacts[0]).read_text(encoding="utf-8"))
    assert payload["errored_count"] == 0
    assert payload["n_tasks"] == 2
    assert payload["cost_is_measured"] is True
    assert all(t["errored"] is False for t in payload["tasks"])
