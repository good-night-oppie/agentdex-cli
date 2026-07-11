"""``adx measure`` — run an AgentCandidate on a ladder and emit MeasureResult JSON.

Two-class ladder taxonomy (ADR-0015 D4):
  - live_adversarial — e.g. arc-agi-3, pokeagent-gen1ou, kaggle
  - static           — e.g. tb2, swe-bench-pro, webarena

Engine selection
----------------
``--engine-fake`` / ``--engine fake`` wires deterministic in-repo stubs so the
path is demonstrable before real ARC / Harbor clients exist. Fake-engine
results are NEVER leaderboard-eligible: receipts are forced to
``tier=self_reported`` / ``kind=fake_engine``.

``--engine local-arc`` wires the genuine local ARC-style grid engine for
``arc-agi-3`` only (measured $0 cost, honest self_reported / no-scorecard
receipt — still NOT leaderboard-eligible, but not a hardcoded-score stub).

``--engine harbor-cli`` wires the real Harbor CLI client for ``tb2``
(subprocess + process-group kill). Requires ``harbor`` on PATH
(``uv tool install harbor``). A missing binary surfaces a clean error,
not a traceback. Paid LLM runs are an operator decision — this engine
only constructs the client.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adx_frontier.candidate import CandidateValidationError, load_candidate
from adx_ladders.adapters.arc_agi3 import ArcAgi3Adapter
from adx_ladders.adapters.tb2_harbor import Tb2HarborAdapter
from adx_ladders.base import MeasureResult, Receipt
from adx_ladders.engines.harbor_cli import HarborCliClient
from adx_ladders.engines.local_arc import LocalArcEngine
from adx_ladders.registry import LadderEntry, load_registry

from agentdex_cli._fakes import FakeArcEngine, FakeHarbor

# Exit codes (WU-5 contract).
_EXIT_OK = 0
_EXIT_GATE = 2
_EXIT_NO_ADAPTER = 3

_ENGINE_FAKE = "fake"
_ENGINE_LOCAL_ARC = "local-arc"
_ENGINE_HARBOR_CLI = "harbor-cli"


def _serialize_measure_result(result: MeasureResult, *, measured_at_utc: str) -> dict[str, Any]:
    return {
        "ladder_id": result.ladder_id,
        "base_model": result.base_model,
        "scores": dict(result.scores),
        "cost_is_measured": result.cost_is_measured,
        "receipt": {
            "tier": result.receipt.tier,
            "kind": result.receipt.kind,
            "ref": result.receipt.ref,
            "artifacts": list(result.receipt.artifacts),
        },
        "budget": {
            "usd": result.budget_usd,
            "wall_clock_min": result.budget_wall_clock_min,
        },
        "measured_at_utc": measured_at_utc,
    }


def _force_fake_receipt(result: MeasureResult) -> MeasureResult:
    """Force NOT-FOR-LEADERBOARD receipt shape on every --engine-fake run."""
    artifacts = result.receipt.artifacts
    if not artifacts:
        artifacts = ("fake_engine:not-for-leaderboard",)
    return replace(
        result,
        receipt=Receipt(
            tier="self_reported",
            kind="fake_engine",
            ref="",
            artifacts=artifacts,
        ),
    )


def _resolve_engine_mode(args: argparse.Namespace) -> str | None:
    """Resolve ``--engine-fake`` + ``--engine`` into a mode string or None.

    Conflict detection (``--engine-fake`` + explicit non-fake ``--engine``)
    lives in ``cmd_measure`` so it can return ``_EXIT_GATE``; this helper
    assumes the caller has already rejected that conflict. Same-intent
    pairs (``--engine-fake`` alone, ``--engine fake``, or both) resolve to
    ``fake``.
    """
    if getattr(args, "engine_fake", False):
        return _ENGINE_FAKE
    engine = getattr(args, "engine", None)
    if engine:
        return str(engine)
    return None


def _engine_fake_conflict(args: argparse.Namespace) -> str | None:
    """Return a conflict message if ``--engine-fake`` fights a real ``--engine``.

    ``--engine-fake --engine fake`` is same-intent and allowed (returns None).
    """
    if not getattr(args, "engine_fake", False):
        return None
    engine = getattr(args, "engine", None)
    if engine is None or str(engine) == _ENGINE_FAKE:
        return None
    return (
        f"--engine-fake conflicts with --engine {engine!r}; "
        "pass one engine selection, or use --engine fake / --engine-fake alone"
    )


def _parse_harbor_tasks(raw: str | None) -> tuple[str, ...] | None:
    """Parse ``--harbor-tasks`` into a non-empty tuple, or ``None`` if unset.

    Empty / whitespace-only items raise ``ValueError`` (caller maps to exit 2).
    Task ids pass through verbatim (including org-prefixed ``org/name``
    forms). Filesystem safety for job/log paths lives in
    ``HarborCliClient`` (``_fs_slug``) — do not rewrite ids into globs here.
    """
    if raw is None:
        return None
    parts = [p.strip() for p in str(raw).split(",")]
    if not parts or any(not p for p in parts):
        raise ValueError(
            "--harbor-tasks requires a non-empty comma-separated list of "
            "task names (empty/whitespace items are rejected)"
        )
    return tuple(parts)


def _build_adapter(
    ladder_id: str,
    *,
    engine_mode: str | None,
    harbor_tasks: tuple[str, ...] | None = None,
    jobs_dir: str | Path | None = None,
):
    if engine_mode is None:
        raise RuntimeError(
            "real hosted ladder engines are not wired yet; pass "
            "--engine-fake / --engine fake for a deterministic local demo "
            "(NOT leaderboard-eligible), --engine local-arc for the "
            "genuine local ARC-style engine on arc-agi-3, or "
            "--engine harbor-cli for the real Harbor CLI client on tb2"
        )
    if engine_mode == _ENGINE_FAKE:
        if ladder_id == "arc-agi-3":
            return ArcAgi3Adapter(FakeArcEngine(), game_ids=["game-0"])
        if ladder_id == "tb2":
            return Tb2HarborAdapter(FakeHarbor(), suite="default")
        raise RuntimeError(
            f"no run-adapter implementation for ladder {ladder_id!r} "
            f"(v1 CLI wires arc-agi-3 and tb2 only)"
        )
    if engine_mode == _ENGINE_LOCAL_ARC:
        if ladder_id != "arc-agi-3":
            raise RuntimeError(
                f"--engine local-arc only supports ladder 'arc-agi-3' (got {ladder_id!r})"
            )
        # cost_dollar=0.0 → measured $0 (no LLM); scorecard_id is None →
        # honest self_reported receipt (never leaderboard-eligible).
        return ArcAgi3Adapter(
            LocalArcEngine(),
            game_ids=["game-0"],
            cost_dollar=0.0,
        )
    if engine_mode == _ENGINE_HARBOR_CLI:
        if ladder_id != "tb2":
            raise RuntimeError(
                f"--engine harbor-cli only supports ladder 'tb2' (got {ladder_id!r})"
            )
        # FileNotFoundError (missing harbor binary) propagates to cmd_measure
        # for a clean stderr message — never a traceback.
        # jobs_dir=None → HarborCliClient mkdtemp default (ephemeral CLI use).
        return Tb2HarborAdapter(
            HarborCliClient(tasks=harbor_tasks, jobs_dir=jobs_dir),
            suite="default",
        )
    raise RuntimeError(f"unknown engine mode: {engine_mode!r}")


def cmd_measure(args: argparse.Namespace) -> int:
    agent_dir = Path(args.agent)
    ladder_id = str(args.ladder)

    # P3 #11: never silently override an explicit real --engine with --engine-fake.
    conflict = _engine_fake_conflict(args)
    if conflict is not None:
        print(conflict, file=sys.stderr)
        return _EXIT_GATE

    engine_mode = _resolve_engine_mode(args)

    # --harbor-tasks / --jobs-dir are harbor-cli only; reject empty items and
    # wrong engines with the same exit-2 gate convention.
    harbor_tasks_raw = getattr(args, "harbor_tasks", None)
    if harbor_tasks_raw is not None and engine_mode != _ENGINE_HARBOR_CLI:
        print(
            f"--harbor-tasks requires --engine harbor-cli (got engine={engine_mode!r})",
            file=sys.stderr,
        )
        return _EXIT_GATE
    jobs_dir_raw = getattr(args, "jobs_dir", None)
    if jobs_dir_raw is not None and engine_mode != _ENGINE_HARBOR_CLI:
        print(
            f"--jobs-dir requires --engine harbor-cli (got engine={engine_mode!r})",
            file=sys.stderr,
        )
        return _EXIT_GATE
    try:
        harbor_tasks = _parse_harbor_tasks(harbor_tasks_raw)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_GATE

    # P2 #10: harbor-cli without --harbor-tasks is a user error (exit 2), not
    # an internal list_tasks ValueError (exit 1). Catch below stays as backstop.
    if engine_mode == _ENGINE_HARBOR_CLI and harbor_tasks is None:
        print(
            "--engine harbor-cli requires --harbor-tasks <task[,task...]>",
            file=sys.stderr,
        )
        return _EXIT_GATE

    jobs_dir: Path | None = Path(jobs_dir_raw) if jobs_dir_raw is not None else None

    try:
        candidate = load_candidate(agent_dir)
    except CandidateValidationError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_GATE

    # Pre-run gate before any engine work (WU-5 §1).
    try:
        candidate.validate()
    except CandidateValidationError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_GATE

    registry = load_registry()
    try:
        entry = registry.get_ladder(ladder_id)
    except KeyError:
        print(
            f"unknown ladder id: {ladder_id!r}; known={[e.id for e in registry.ladders]}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(entry, LadderEntry):
        print(f"registry id {ladder_id!r} is not a ladder", file=sys.stderr)
        return 1

    if not entry.run_adapter:
        print(
            f"ladder {ladder_id!r} has run_adapter=false "
            f"(curated link-out only; no local measure path)",
            file=sys.stderr,
        )
        return _EXIT_NO_ADAPTER

    try:
        adapter = _build_adapter(
            ladder_id,
            engine_mode=engine_mode,
            harbor_tasks=harbor_tasks,
            jobs_dir=jobs_dir,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_NO_ADAPTER
    except FileNotFoundError as exc:
        # harbor-cli missing binary → actionable message, no traceback.
        print(str(exc), file=sys.stderr)
        return _EXIT_NO_ADAPTER

    # Adapter pre_run_check re-validates + confirms ladder ∈ candidate.ladders.
    try:
        adapter.pre_run_check(candidate)
    except CandidateValidationError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_GATE
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        result = adapter.measure(candidate)
    except ValueError as exc:
        # Backstop: HarborCliClient.list_tasks with no injected tasks= (P2 #10
        # user-error family → exit 2, never a raw traceback).
        print(str(exc), file=sys.stderr)
        return _EXIT_GATE
    if engine_mode == _ENGINE_FAKE:
        result = _force_fake_receipt(result)

    measured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = _serialize_measure_result(result, measured_at_utc=measured_at)
    # RFC-8259: never emit bare NaN/Infinity tokens (allow_nan=False).
    try:
        text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    except (ValueError, TypeError) as exc:
        print(
            f"measure result is not JSON-serializable under RFC-8259: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")

    sys.stdout.write(text)
    return _EXIT_OK


def register_measure_parser(subs: argparse._SubParsersAction) -> None:
    measure = subs.add_parser(
        "measure",
        help=(
            "Measure an AgentCandidate on a ladder (Pareto axes). "
            "Two-class taxonomy: live_adversarial vs static. "
            "--engine-fake demos are NEVER leaderboard-eligible."
        ),
        description=(
            "Run ``adx measure --agent <dir> --ladder <id>`` to validate the "
            "candidate, execute the ladder adapter, and emit a MeasureResult "
            "JSON (scores keyed by FRONTIER_AXES + receipt + budget).\n\n"
            "Ladder taxonomy (ADR-0015):\n"
            "  live_adversarial — adversarial refresh is the contamination guard\n"
            "  static           — fixed test sets; held-out / decontam required\n\n"
            "Engine selection:\n"
            "  --engine-fake / --engine fake — deterministic in-repo stubs; "
            "receipts forced to kind=fake_engine (NEVER leaderboard-eligible)\n"
            "  --engine local-arc — genuine local ARC-style grid engine for "
            "arc-agi-3; measured $0 cost; honest self_reported receipt "
            "(still not leaderboard-eligible — no scorecard authority)\n"
            "  --engine harbor-cli — real Harbor CLI client for tb2 "
            "(requires `uv tool install harbor`; paid LLM runs are operator-gated)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    measure.add_argument(
        "--agent",
        required=True,
        help="path to AgentCandidate directory (must contain candidate.yaml)",
    )
    measure.add_argument(
        "--ladder",
        required=True,
        help="ladder id from the curated registry (e.g. arc-agi-3, tb2)",
    )
    measure.add_argument(
        "--out",
        default=None,
        help="optional path to also write the MeasureResult JSON",
    )
    measure.add_argument(
        "--engine",
        choices=[_ENGINE_FAKE, _ENGINE_LOCAL_ARC, _ENGINE_HARBOR_CLI],
        default=None,
        help=(
            "engine backend: 'fake' (NOT-FOR-LEADERBOARD stubs), "
            "'local-arc' (genuine local ARC-style grid, arc-agi-3 only), or "
            "'harbor-cli' (real Harbor CLI client, tb2 only)"
        ),
    )
    measure.add_argument(
        "--engine-fake",
        action="store_true",
        help=(
            "use deterministic in-repo fake engines (NOT-FOR-LEADERBOARD; "
            "receipts forced to kind=fake_engine). Alias for --engine fake."
        ),
    )
    measure.add_argument(
        "--harbor-tasks",
        default=None,
        help=(
            "comma-separated Harbor task names injected into HarborCliClient "
            "(--engine harbor-cli only; required for real TB2 runs because "
            "harbor has no task-list CLI surface)"
        ),
    )
    measure.add_argument(
        "--jobs-dir",
        default=None,
        help=(
            "durable directory for Harbor job artifacts (--engine harbor-cli "
            "only). When omitted, HarborCliClient uses an ephemeral mkdtemp "
            "under /tmp; pass this so self_reported receipt paths survive."
        ),
    )
    measure.set_defaults(func=cmd_measure)
