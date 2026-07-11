"""ARC-AGI-3 ladder run-adapter (ADR-0015 D3/D5/D6).

Out-of-process line-delimited JSON stdio protocol
-------------------------------------------------
The candidate ``entrypoint`` is spawned as a subprocess (cwd = candidate
root). The adapter and candidate exchange one JSON object per line on
stdin/stdout:

Adapter → candidate (observation)::

    {"type": "observation", "game": "<game_id>", "frame": <engine-frame>}

Candidate → adapter (action)::

    {"type": "action", "action": <opaque-action>}

Episodes: for each ``game_id``, the adapter calls ``engine.reset(game_id)``,
sends an observation, then loops ``read action → engine.step(action) →
send observation`` until the engine reports ``done`` or ``max_steps_per_episode``
is hit. Wall-clock is enforced against ``candidate.budget.wall_clock_min``;
on exceed the subprocess is killed, ``quality`` is reported as ``0.0``, and
a ``MeasureResult`` is still returned (honest, not dropped).

The real ``arc-agi`` SDK is NOT imported here. Callers inject an
``ArcEngineProtocol`` (local fake in unit tests; hosted/local engine wrapper
in a later integration WU).
"""

from __future__ import annotations

import json
import os
import select
import shlex
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from adx_frontier.candidate import AgentCandidate
from adx_ladders.base import LadderAdapter, LadderClass, MeasureResult, Receipt

_KILL_GRACE_SEC = 0.5


class ArcEngineProtocol(Protocol):
    """Thin engine surface — no network assumed; hosted client is injected."""

    def reset(self, game_id: str) -> Mapping[str, Any]:
        """Start an episode; return a mapping that includes ``frame``."""

    def step(self, action: Any) -> Mapping[str, Any]:
        """Apply ``action``; return mapping with ``frame`` and ``done`` (bool)."""

    def score(self) -> float:
        """Aggregate quality in ``[0, 1]``."""

    def scorecard_id(self) -> str | None:
        """Hosted scorecard id when verified; ``None`` → self-reported path."""


class ArcAgi3Adapter(LadderAdapter):
    """Run an AgentCandidate against ARC-AGI-3 via an injected engine."""

    ladder_id = "arc-agi-3"
    ladder_class = LadderClass.LIVE_ADVERSARIAL

    def __init__(
        self,
        engine: ArcEngineProtocol,
        game_ids: Sequence[str] | None = None,
        *,
        cost_dollar: float | None = None,
        max_steps_per_episode: int = 64,
    ) -> None:
        self._engine = engine
        self._game_ids = tuple(game_ids) if game_ids else ("game-0",)
        self._cost_dollar = cost_dollar
        self._max_steps = max_steps_per_episode

    def measure(self, candidate: AgentCandidate) -> MeasureResult:
        self.pre_run_check(candidate)

        budget_sec = float(candidate.budget.wall_clock_min) * 60.0
        started = time.monotonic()
        deadline = started + budget_sec

        episodes: list[dict[str, Any]] = []
        actions_total = 0
        timed_out = False
        proc: subprocess.Popen[str] | None = None

        try:
            proc = self._spawn(candidate)
            for game_id in self._game_ids:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                if proc.poll() is not None:
                    break

                ep = self._run_episode(
                    proc=proc,
                    game_id=game_id,
                    deadline=deadline,
                )
                episodes.append(ep)
                actions_total += int(ep["actions"])
                if ep.get("timed_out"):
                    timed_out = True
                    break
        finally:
            if proc is not None and proc.poll() is None:
                self._kill(proc)

        wall_clock_sec = max(time.monotonic() - started, 0.0)
        if timed_out:
            quality = 0.0
        else:
            quality = float(self._engine.score())

        cost_is_measured = self._cost_dollar is not None
        cost = (
            float(self._cost_dollar)
            if cost_is_measured
            else float(candidate.budget.usd)
        )

        artifact_ref = self._write_run_log(
            candidate=candidate,
            episodes=episodes,
            actions_total=actions_total,
            quality=quality,
            cost_dollar=cost,
            cost_is_measured=cost_is_measured,
            wall_clock_sec=wall_clock_sec,
            timed_out=timed_out,
        )

        scorecard = self._engine.scorecard_id()
        if scorecard and not timed_out:
            receipt = Receipt(
                tier="verified",
                kind="arc_scorecard_id",
                ref=str(scorecard),
            )
        else:
            receipt = Receipt(
                tier="self_reported",
                kind="raw_artifacts",
                ref="",
                artifacts=(str(artifact_ref),),
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
            cost_is_measured=cost_is_measured,
        )

    def _spawn(self, candidate: AgentCandidate) -> subprocess.Popen[str]:
        argv = shlex.split(candidate.entrypoint)
        if not argv:
            raise ValueError("candidate.entrypoint is empty after shlex.split")
        return subprocess.Popen(
            argv,
            cwd=str(candidate.root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

    def _run_episode(
        self,
        *,
        proc: subprocess.Popen[str],
        game_id: str,
        deadline: float,
    ) -> dict[str, Any]:
        reset_obs = dict(self._engine.reset(game_id))
        frame = reset_obs.get("frame", reset_obs)
        actions = 0
        timed_out = False
        done = bool(reset_obs.get("done", False))

        remaining = deadline - time.monotonic()
        if not self._send_observation(proc, game_id, frame, remaining):
            timed_out = time.monotonic() >= deadline
            return {
                "game": game_id,
                "actions": 0,
                "done": False,
                "timed_out": timed_out,
                "error": "send_timeout" if timed_out else "send_failed",
            }

        while not done and actions < self._max_steps:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break

            action_msg = self._read_action(proc, remaining)
            if action_msg is None:
                # select waited out the remaining budget, or the process
                # exited / emitted a non-action line. Only the former is a
                # budget kill.
                timed_out = time.monotonic() >= deadline
                break

            action = action_msg.get("action")
            step_obs = dict(self._engine.step(action))
            actions += 1
            done = bool(step_obs.get("done", False))
            if done:
                break

            frame = step_obs.get("frame", step_obs)
            remaining = deadline - time.monotonic()
            if not self._send_observation(proc, game_id, frame, remaining):
                timed_out = time.monotonic() >= deadline
                break

            if time.monotonic() >= deadline:
                timed_out = True
                break

        return {
            "game": game_id,
            "actions": actions,
            "done": done,
            "timed_out": timed_out,
        }

    def _send_observation(
        self,
        proc: subprocess.Popen[str],
        game_id: str,
        frame: Any,
        timeout_sec: float,
    ) -> bool:
        """Write one observation line; bound by ``timeout_sec`` (never hang).

        A full OS pipe buffer + a non-reading child blocks ``write``/``flush``.
        Bound the write with a daemon thread joined against the remaining
        wall-clock budget so the parent can kill and return timed-out.
        """
        if proc.stdin is None or proc.poll() is not None:
            return False
        if timeout_sec <= 0:
            return False
        line = json.dumps(
            {"type": "observation", "game": game_id, "frame": frame},
            separators=(",", ":"),
        )
        payload = line + "\n"
        errors: list[BaseException] = []

        def _write() -> None:
            try:
                assert proc.stdin is not None
                proc.stdin.write(payload)
                proc.stdin.flush()
            except BaseException as exc:  # noqa: BLE001 — surface to joiner
                errors.append(exc)

        writer = threading.Thread(target=_write, daemon=True)
        writer.start()
        writer.join(timeout=timeout_sec)
        if writer.is_alive():
            return False
        return not errors

    def _read_action(
        self,
        proc: subprocess.Popen[str],
        timeout_sec: float,
    ) -> dict[str, Any] | None:
        if proc.stdout is None:
            return None
        if timeout_sec <= 0:
            return None

        ready, _, _ = select.select([proc.stdout], [], [], timeout_sec)
        if not ready:
            return None

        raw = proc.stdout.readline()
        if not raw:
            return None
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(msg, dict) or msg.get("type") != "action":
            return None
        return msg

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

        _signal_group(signal.SIGTERM)
        try:
            proc.wait(timeout=_KILL_GRACE_SEC)
        except subprocess.TimeoutExpired:
            _signal_group(signal.SIGKILL)
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        # Drain pipes to avoid zombie fd pressure in long test suites.
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass

    def _write_run_log(
        self,
        *,
        candidate: AgentCandidate,
        episodes: list[dict[str, Any]],
        actions_total: int,
        quality: float,
        cost_dollar: float,
        cost_is_measured: bool,
        wall_clock_sec: float,
        timed_out: bool,
    ) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"arc-agi-3-{stamp}-{uuid.uuid4().hex[:8]}.json"
        payload = {
            "ladder_id": self.ladder_id,
            "candidate": candidate.name,
            "episodes": episodes,
            "actions_total": actions_total,
            "scores": {
                "quality": quality,
                "cost_dollar": cost_dollar,
                "wall_clock_sec": wall_clock_sec,
            },
            "cost_is_measured": cost_is_measured,
            "timing": {
                "wall_clock_sec": wall_clock_sec,
                "budget_wall_clock_min": candidate.budget.wall_clock_min,
                "timed_out": timed_out,
            },
        }
        text = json.dumps(payload, indent=2) + "\n"

        # Prefer candidate/.adx/runs; fall back to a temp dir (read-only root)
        # then to an in-memory marker so measure() never crashes.
        primary = candidate.root / ".adx" / "runs"
        try:
            primary.mkdir(parents=True, exist_ok=True)
            path = primary / filename
            path.write_text(text, encoding="utf-8")
            return str(path.resolve())
        except OSError:
            pass
        try:
            tmp = Path(tempfile.mkdtemp(prefix="adx-arc-runs-"))
            path = tmp / filename
            path.write_text(text, encoding="utf-8")
            return str(path.resolve())
        except OSError:
            pass
        return f"memory://{filename}"
