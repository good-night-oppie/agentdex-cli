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
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adx_frontier.candidate import CandidateValidationError, load_candidate
from adx_ladders.adapters.arc_agi3 import ArcAgi3Adapter
from adx_ladders.adapters.tb2_harbor import Tb2HarborAdapter
from adx_ladders.base import MeasureResult, Receipt
from adx_ladders.engines.local_arc import LocalArcEngine
from adx_ladders.registry import LadderEntry, load_registry

from agentdex_cli._fakes import FakeArcEngine, FakeHarbor

# Exit codes (WU-5 contract).
_EXIT_OK = 0
_EXIT_GATE = 2
_EXIT_NO_ADAPTER = 3

_ENGINE_FAKE = "fake"
_ENGINE_LOCAL_ARC = "local-arc"


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
    """Resolve ``--engine-fake`` + ``--engine`` into a mode string or None."""
    if getattr(args, "engine_fake", False):
        return _ENGINE_FAKE
    engine = getattr(args, "engine", None)
    if engine:
        return str(engine)
    return None


def _build_adapter(ladder_id: str, *, engine_mode: str | None):
    if engine_mode is None:
        raise RuntimeError(
            "real hosted ladder engines are not wired yet; pass "
            "--engine-fake / --engine fake for a deterministic local demo "
            "(NOT leaderboard-eligible), or --engine local-arc for the "
            "genuine local ARC-style engine on arc-agi-3"
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
                f"--engine local-arc only supports ladder 'arc-agi-3' "
                f"(got {ladder_id!r})"
            )
        # cost_dollar=0.0 → measured $0 (no LLM); scorecard_id is None →
        # honest self_reported receipt (never leaderboard-eligible).
        return ArcAgi3Adapter(
            LocalArcEngine(),
            game_ids=["game-0"],
            cost_dollar=0.0,
        )
    raise RuntimeError(f"unknown engine mode: {engine_mode!r}")


def cmd_measure(args: argparse.Namespace) -> int:
    agent_dir = Path(args.agent)
    ladder_id = str(args.ladder)
    engine_mode = _resolve_engine_mode(args)

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
            f"unknown ladder id: {ladder_id!r}; "
            f"known={[e.id for e in registry.ladders]}",
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
        adapter = _build_adapter(ladder_id, engine_mode=engine_mode)
    except RuntimeError as exc:
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

    result = adapter.measure(candidate)
    if engine_mode == _ENGINE_FAKE:
        result = _force_fake_receipt(result)

    measured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            "(still not leaderboard-eligible — no scorecard authority)"
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
        choices=[_ENGINE_FAKE, _ENGINE_LOCAL_ARC],
        default=None,
        help=(
            "engine backend: 'fake' (NOT-FOR-LEADERBOARD stubs) or "
            "'local-arc' (genuine local ARC-style grid, arc-agi-3 only)"
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
    measure.set_defaults(func=cmd_measure)
