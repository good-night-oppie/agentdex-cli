"""Real Harbor CLI client implementing ``HarborProtocol`` (M2 WU-8).

Grounded in the installed ``harbor`` CLI surface captured at
``.fleet-goal/evidence/M2/harbor-cli-surface.md`` (harbor 0.18.0).

Invocation shape (per-task)::

    harbor run \\
      -d <dataset> \\
      -i <task_id> \\
      -o <jobs_dir> \\
      --job-name <unique> \\
      -a <agent|module:Class> \\
      [-m <model>] \\
      -n 1 \\
      -l 1

``-n 1`` is concurrency (``--n-concurrent``); ``-l 1`` is the hard
task cap (``--n-tasks``) so a globbing ``-i`` cannot expand past one
task. No per-dataset task-id listing exists on the CLI
(``harbor dataset list`` lists registries, not tasks). ``list_tasks``
therefore returns the constructor-injected ``tasks`` tuple, or raises
``ValueError`` when ``tasks is None``.

Subprocess hardening mirrors ``arc_agi3._spawn`` / ``_kill`` (WU-6):
``stdin=DEVNULL``, ``start_new_session=True``, SIGTERM→grace→SIGKILL on
the whole process group. Timed-out runs return
``HarborTaskResult(passed=False, timed_out=True, ...)`` — never raise.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path

from adx_ladders.adapters.tb2_harbor import HarborTaskResult

_KILL_GRACE_SEC = 0.5
_MISSING_BIN_HINT = "harbor binary not found; install with: uv tool install harbor"


def _fs_slug(task_id: str) -> str:
    """Filesystem-safe slug: chars outside ``[A-Za-z0-9._-]`` → ``_``.

    Used only for on-disk ``job_name`` / ``.harbor.log`` paths. The exact
    ``task_id`` (org-prefixed forms included) still goes to harbor ``-i``
    and to ``_parse_job_result`` matching — never rewrite the filter.
    """
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in task_id)


class HarborCliClient:
    """Thin subprocess wrapper around the real ``harbor`` CLI."""

    def __init__(
        self,
        *,
        harbor_bin: str = "harbor",
        dataset: str = "terminal-bench/terminal-bench-2",
        jobs_dir: str | Path | None = None,
        tasks: Sequence[str] | None = None,
        agent_import_path: str | None = None,
        model: str | None = None,
    ) -> None:
        self._harbor_bin = harbor_bin
        self._dataset = dataset
        self._tasks: tuple[str, ...] | None = tuple(tasks) if tasks is not None else None
        self._agent_import_path = agent_import_path
        self._model = model
        if jobs_dir is None:
            self._jobs_dir = Path(tempfile.mkdtemp(prefix="adx-harbor-jobs-"))
        else:
            self._jobs_dir = Path(jobs_dir)
            self._jobs_dir.mkdir(parents=True, exist_ok=True)
        # Fail closed early when the binary is missing (construction-time).
        self._resolved_bin = self._resolve_bin()

    @property
    def jobs_dir(self) -> Path:
        return self._jobs_dir

    def list_tasks(self, suite: str) -> list[str]:
        """Return injected task ids; no real CLI listing surface exists."""
        del suite  # suite is adapter-forwarded; listing is constructor-injected
        if self._tasks is None:
            raise ValueError(
                "HarborCliClient.list_tasks: no task-list CLI surface for a "
                "dataset (harbor dataset list lists registries, not task ids). "
                "Pass tasks=(...) to HarborCliClient(...) to inject the suite."
            )
        return list(self._tasks)

    def run_task(
        self,
        task_id: str,
        agent_cmd: str,
        timeout_sec: float,
    ) -> HarborTaskResult:
        """Run one Harbor task; kill the process group on timeout.

        ``-i`` receives ``task_id`` exactly (org-prefixed ids included).
        On-disk ``job_name`` and ``.harbor.log`` use ``_fs_slug(task_id)``
        so a ``/`` in the id cannot break ``open()``.
        """
        job_name = f"adx-{_fs_slug(task_id)}-{uuid.uuid4().hex[:8]}"
        agent = self._agent_import_path or agent_cmd
        argv = [
            self._resolved_bin,
            "run",
            "-d",
            self._dataset,
            "-i",
            task_id,
            "-o",
            str(self._jobs_dir),
            "--job-name",
            job_name,
            "-a",
            agent,
            "-n",
            "1",
            "-l",
            "1",
        ]
        if self._model:
            argv.extend(["-m", self._model])

        # Drain child stdout+stderr to disk — PIPE + bare wait() deadlocks
        # once the OS pipe buffer (~64KB) fills (WU-8F F1).
        harbor_log = self._jobs_dir / f"{job_name}.harbor.log"
        log_fh = open(harbor_log, "w", encoding="utf-8")
        try:
            try:
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except FileNotFoundError as exc:
                raise FileNotFoundError(_MISSING_BIN_HINT) from exc

            timed_out = False
            try:
                proc.wait(timeout=max(float(timeout_sec), 0.0))
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill(proc)
        finally:
            log_fh.close()

        job_dir = self._jobs_dir / job_name
        if timed_out:
            return HarborTaskResult(
                passed=False,
                log_path=str(self._jobs_dir),
                cost_dollar=None,
                timed_out=True,
            )

        return self._parse_job_result(job_dir, task_id=task_id)

    def _resolve_bin(self) -> str:
        candidate = Path(self._harbor_bin)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        found = shutil.which(self._harbor_bin)
        if found:
            return found
        raise FileNotFoundError(_MISSING_BIN_HINT)

    def _parse_job_result(self, job_dir: Path, *, task_id: str) -> HarborTaskResult:
        trial_result_path = self._find_trial_result(job_dir, task_id=task_id)
        if trial_result_path is None:
            log = str(job_dir if job_dir.is_dir() else self._jobs_dir)
            return HarborTaskResult(
                passed=False,
                log_path=log,
                cost_dollar=None,
                timed_out=False,
            )

        try:
            data = json.loads(trial_result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return HarborTaskResult(
                passed=False,
                log_path=str(trial_result_path.parent),
                cost_dollar=None,
                timed_out=False,
            )

        passed = self._reward_passed(data)
        cost = self._extract_cost(data)
        return HarborTaskResult(
            passed=passed,
            log_path=str(trial_result_path.parent),
            cost_dollar=cost,
            timed_out=False,
        )

    @staticmethod
    def _find_trial_result(job_dir: Path, *, task_id: str) -> Path | None:
        if not job_dir.is_dir():
            return None
        matches: list[Path] = []
        fallback: list[Path] = []
        for path in job_dir.rglob("result.json"):
            if path.parent == job_dir:
                continue  # job-level JobResult
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("task_name") == task_id:
                matches.append(path)
            elif "verifier_result" in payload or "task_name" in payload:
                fallback.append(path)
        if matches:
            return matches[0]
        if len(fallback) == 1:
            return fallback[0]
        return None

    @staticmethod
    def _reward_passed(data: dict[object, object]) -> bool:
        """Harbor analyzer pass: ``verifier_result.rewards['reward'] == 1``."""
        verifier = data.get("verifier_result")
        if not isinstance(verifier, dict):
            return False
        rewards = verifier.get("rewards")
        if not isinstance(rewards, dict):
            return False
        reward = rewards.get("reward", 0)
        try:
            return float(reward) == 1.0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _extract_cost(data: dict[object, object]) -> float | None:
        """Propagate ``agent_result.cost_usd`` when present; never fabricate."""
        agent = data.get("agent_result")
        if not isinstance(agent, dict):
            return None
        cost = agent.get("cost_usd")
        if cost is None:
            return None
        try:
            return float(cost)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _kill(proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        pgid: int | None
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = None

        def _signal_group(sig: signal.Signals) -> None:
            if pgid is not None:
                try:
                    os.killpg(pgid, sig)
                    return
                except OSError:
                    pass
            try:
                proc.send_signal(sig)
            except OSError:
                pass

        # SIGTERM first, then always escalate to SIGKILL after grace.
        # Grandchildren may ignore SIGTERM (and outlive a parent that exits
        # cleanly on SIGTERM); only a group SIGKILL reaps them.
        _signal_group(signal.SIGTERM)
        try:
            proc.wait(timeout=_KILL_GRACE_SEC)
        except subprocess.TimeoutExpired:
            pass
        _signal_group(signal.SIGKILL)
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
