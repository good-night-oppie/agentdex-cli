"""``adx evolve-submit`` — submit a measured AgentCandidate through Bene + export frontier.

Consumes a durable ``adx measure`` JSON artifact (does not re-measure). Bridges
via ``adx_frontier.mh_bridge.bridge_collaborative_candidate``; ACCEPT is the only
promoted state, decided exclusively by Bene's kill gate.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from adx_frontier.candidate import (
    FRONTIER_AXES,
    AgentCandidate,
    CandidateValidationError,
    load_candidate,
)
from adx_frontier.ledger import (
    FrontierLedger,
    FrontierRecord,
    PromotionReceipt,
    TrustReceipt,
)
from adx_frontier.mh_bridge import BeneApi, BridgeOutcome, bridge_collaborative_candidate

_EXIT_OK = 0
_EXIT_GATE = 2
_EXIT_BENE = 3

_BENE_INSTALL_HINT = "pip install 'agentdex-cli[bene]'"


class EvolveSubmitError(ValueError):
    """Validation or Bene-boundary failure with a safe, operator-facing message."""

    def __init__(self, message: str, *, exit_code: int = _EXIT_GATE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _load_json(path: Path, label: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvolveSubmitError(f"cannot read {label}: {path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvolveSubmitError(f"malformed {label} JSON: {path}") from exc


def _finite_axes(values: Any, label: str) -> dict[str, float]:
    if not isinstance(values, dict):
        raise EvolveSubmitError(f"{label} must be a mapping of frontier axes")
    missing = [axis for axis in FRONTIER_AXES if axis not in values]
    if missing:
        raise EvolveSubmitError(f"{label} missing frontier axes: {missing}")
    extra = [key for key in values if key not in FRONTIER_AXES]
    if extra:
        raise EvolveSubmitError(f"{label} has unknown frontier axes: {extra}")
    result: dict[str, float] = {}
    for axis in FRONTIER_AXES:
        raw = values[axis]
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise EvolveSubmitError(f"{label}.{axis} must be a finite number")
        value = float(raw)
        if not math.isfinite(value):
            raise EvolveSubmitError(f"{label}.{axis} must be a finite number")
        result[axis] = value
    return result


def _load_baseline_axes(path: Path) -> dict[str, float]:
    payload = _load_json(path, "baseline")
    if isinstance(payload, dict) and "scores" in payload:
        return _finite_axes(payload["scores"], "baseline.scores")
    return _finite_axes(payload, "baseline")


def _parse_artifact_list(raw: Any, *, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise EvolveSubmitError(f"{label} must be a list of strings")
    artifacts: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise EvolveSubmitError(f"{label} entries must be strings")
        artifacts.append(item)
    return tuple(artifacts)


def _parse_trust_receipt(raw: Any) -> TrustReceipt:
    if not isinstance(raw, dict):
        raise EvolveSubmitError("measurement.receipt must be a mapping")
    tier = raw.get("tier")
    kind = raw.get("kind")
    if not isinstance(tier, str) or not isinstance(kind, str):
        raise EvolveSubmitError("measurement.receipt requires string tier and kind")
    ref = raw.get("ref", "")
    if ref is None:
        ref = ""
    if not isinstance(ref, str):
        raise EvolveSubmitError("measurement.receipt.ref must be a string")
    artifacts = _parse_artifact_list(
        raw.get("artifacts", ()), label="measurement.receipt.artifacts"
    )
    try:
        return TrustReceipt(tier=tier, kind=kind, ref=ref, artifacts=artifacts)
    except ValueError as exc:
        raise EvolveSubmitError(f"measurement.receipt invalid: {exc}") from exc


def _parse_measurement(path: Path) -> dict[str, Any]:
    payload = _load_json(path, "measurement")
    if not isinstance(payload, dict):
        raise EvolveSubmitError("measurement JSON must be a mapping")
    for key in ("ladder_id", "base_model", "scores", "receipt", "budget", "measured_at_utc"):
        if key not in payload:
            raise EvolveSubmitError(f"measurement missing required field {key!r}")
    ladder_id = payload["ladder_id"]
    base_model = payload["base_model"]
    measured_at = payload["measured_at_utc"]
    if not isinstance(ladder_id, str) or not ladder_id.strip():
        raise EvolveSubmitError("measurement.ladder_id must be a non-empty string")
    if not isinstance(base_model, str) or not base_model.strip():
        raise EvolveSubmitError("measurement.base_model must be a non-empty string")
    if not isinstance(measured_at, str) or not measured_at.strip():
        raise EvolveSubmitError("measurement.measured_at_utc must be a non-empty string")
    scores = _finite_axes(payload["scores"], "measurement.scores")
    receipt = _parse_trust_receipt(payload["receipt"])
    budget = payload["budget"]
    if not isinstance(budget, dict) or "usd" not in budget or "wall_clock_min" not in budget:
        raise EvolveSubmitError("measurement.budget must include usd and wall_clock_min")
    try:
        budget_usd = float(budget["usd"])
        budget_wall = float(budget["wall_clock_min"])
    except (TypeError, ValueError) as exc:
        raise EvolveSubmitError("measurement.budget values must be numbers") from exc
    if isinstance(budget["usd"], bool) or isinstance(budget["wall_clock_min"], bool):
        raise EvolveSubmitError("measurement.budget values must be numbers")
    if not math.isfinite(budget_usd) or not math.isfinite(budget_wall):
        raise EvolveSubmitError("measurement.budget values must be finite")
    candidate_name = payload.get("candidate")
    if candidate_name is not None and not isinstance(candidate_name, str):
        raise EvolveSubmitError("measurement.candidate must be a string when present")
    return {
        "ladder_id": ladder_id,
        "base_model": base_model,
        "scores": scores,
        "receipt": receipt,
        "budget_usd": budget_usd,
        "budget_wall_clock_min": budget_wall,
        "measured_at_utc": measured_at,
        "candidate": candidate_name,
    }


def _assert_candidate_matches(candidate: AgentCandidate, measurement: dict[str, Any]) -> None:
    if measurement["ladder_id"] not in candidate.ladders:
        raise EvolveSubmitError(
            f"ladder mismatch: measurement ladder {measurement['ladder_id']!r} "
            f"not in candidate.ladders={list(candidate.ladders)}"
        )
    if measurement["base_model"] != candidate.base_model:
        raise EvolveSubmitError(
            f"base_model mismatch: measurement={measurement['base_model']!r} "
            f"candidate={candidate.base_model!r}"
        )
    if measurement["candidate"] is not None and measurement["candidate"] != candidate.name:
        raise EvolveSubmitError(
            f"candidate mismatch: measurement={measurement['candidate']!r} "
            f"candidate={candidate.name!r}"
        )
    if measurement["budget_usd"] != candidate.budget.usd or (
        measurement["budget_wall_clock_min"] != candidate.budget.wall_clock_min
    ):
        raise EvolveSubmitError(
            "budget mismatch: "
            f"measurement usd={measurement['budget_usd']} "
            f"wall_clock_min={measurement['budget_wall_clock_min']} vs "
            f"candidate usd={candidate.budget.usd} "
            f"wall_clock_min={candidate.budget.wall_clock_min}"
        )


def _bene_error(message: str, exc: BaseException | None = None) -> EvolveSubmitError:
    """Stable Bene-boundary error: never echo third-party exception text."""
    if exc is None:
        return EvolveSubmitError(message, exit_code=_EXIT_BENE)
    return EvolveSubmitError(
        f"{message} ({type(exc).__name__})",
        exit_code=_EXIT_BENE,
    )


def open_bene_context(db_path: str | Path, agent_id: str) -> tuple[Any, Any]:
    """Open a Bene DB and return ``(store, conn)`` for a registered ``agent_id``."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise EvolveSubmitError("bene agent_id must be a non-empty string", exit_code=_EXIT_BENE)
    path = Path(db_path)
    if not path.is_file():
        raise EvolveSubmitError(f"bene database not found: {path}", exit_code=_EXIT_BENE)
    try:
        from bene.core import Bene
        from bene.kernel import EngramStore, ensure_v2
    except ImportError as exc:
        raise EvolveSubmitError(
            f"bene is not installed; install with: {_BENE_INSTALL_HINT}",
            exit_code=_EXIT_BENE,
        ) from exc
    try:
        bene = Bene(db_path=str(path))
        ensure_v2(bene.conn)
        row = bene.conn.execute("SELECT 1 FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    except EvolveSubmitError:
        raise
    except Exception as exc:  # noqa: BLE001 — boundary; never echo exception text
        raise _bene_error("bene database error", exc) from None
    if row is None:
        raise EvolveSubmitError(
            f"bene agent_id {agent_id!r} is not registered",
            exit_code=_EXIT_BENE,
        )
    return EngramStore(bene.conn, bene.blobs), bene.conn


def _require_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a bool")
    return value


def _record_from_export_dict(raw: dict[str, Any]) -> FrontierRecord:
    receipt_raw = raw["receipt"]
    if not isinstance(receipt_raw, dict):
        raise ValueError("receipt must be a mapping")
    artifacts = _parse_artifact_list(
        receipt_raw.get("artifacts") or (),
        label="frontier receipt.artifacts",
    )
    promotion_raw = raw.get("promotion")
    promotion = None
    if promotion_raw is not None:
        if not isinstance(promotion_raw, dict):
            raise ValueError("promotion must be a mapping")
        promotion = PromotionReceipt(
            candidate_engram_id=str(promotion_raw["candidate_engram_id"]),
            promoted=_require_bool(promotion_raw["promoted"], label="promotion.promoted"),
            status=str(promotion_raw["status"]),
            verdict_engram=promotion_raw.get("verdict_engram"),
        )
    return FrontierRecord(
        candidate=str(raw["candidate"]),
        ladder_id=str(raw["ladder_id"]),
        base_model=str(raw["base_model"]),
        scores={axis: float(raw["scores"][axis]) for axis in FRONTIER_AXES},
        budget_usd=float(raw["budget_usd"]),
        budget_wall_clock_min=float(raw["budget_wall_clock_min"]),
        receipt=TrustReceipt(
            tier=str(receipt_raw["tier"]),
            kind=str(receipt_raw["kind"]),
            ref=str(receipt_raw.get("ref") or ""),
            artifacts=artifacts,
        ),
        measured_at_utc=str(raw["measured_at_utc"]),
        promotion=promotion,
    )


def _load_or_empty_ledger(path: Path) -> FrontierLedger:
    if not path.exists():
        return FrontierLedger()
    payload = _load_json(path, "frontier")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise EvolveSubmitError(f"unsupported or malformed frontier JSON: {path}")
    records: list[FrontierRecord] = []
    partitions = payload.get("partitions")
    if not isinstance(partitions, list):
        raise EvolveSubmitError(f"malformed frontier partitions: {path}")
    try:
        for part in partitions:
            if not isinstance(part, dict):
                raise ValueError("partition must be a mapping")
            for entry in part.get("frontier") or []:
                if not isinstance(entry, dict):
                    raise ValueError("frontier entry must be a mapping")
                records.append(_record_from_export_dict(entry))
    except EvolveSubmitError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise EvolveSubmitError(f"malformed frontier record in {path}: {exc}") from exc
    return FrontierLedger(records)


def _persist_frontier(
    *,
    out_path: Path,
    record: FrontierRecord,
    promotion: PromotionReceipt,
    generated_at_utc: str | None,
) -> None:
    """Load/merge/export frontier.json; never leak OS/third-party text after verdict."""
    try:
        ledger = _load_or_empty_ledger(out_path)
        ledger.add(record)
        ledger.export(out_path, generated_at_utc=generated_at_utc)
    except EvolveSubmitError as exc:
        raise EvolveSubmitError(
            "frontier persistence failed after Bene verdict "
            f"(promoted={promotion.promoted}, status={promotion.status}): {exc}"
        ) from None
    except OSError:
        raise EvolveSubmitError(
            "frontier persistence failed after Bene verdict "
            f"(promoted={promotion.promoted}, status={promotion.status}): "
            "cannot write frontier output"
        ) from None
    except (TypeError, ValueError) as exc:
        raise EvolveSubmitError(
            "frontier persistence failed after Bene verdict "
            f"(promoted={promotion.promoted}, status={promotion.status}): "
            f"malformed frontier state ({type(exc).__name__})"
        ) from None


def submit_measured_candidate(
    *,
    agent: str | Path,
    measurement: str | Path,
    baseline: str | Path,
    metric: str,
    out: str | Path,
    agent_id: str,
    bene_db: str | Path | None = None,
    store: Any | None = None,
    conn: Any | None = None,
    api: BeneApi | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate, bridge through Bene, persist ``FrontierRecord``, export frontier.json."""
    try:
        candidate = load_candidate(agent)
        candidate.validate()
    except CandidateValidationError as exc:
        raise EvolveSubmitError(str(exc)) from exc

    measured = _parse_measurement(Path(measurement))
    _assert_candidate_matches(candidate, measured)
    baseline_axes = _load_baseline_axes(Path(baseline))
    if not isinstance(metric, str) or not metric.strip():
        raise EvolveSubmitError("metric must be a non-empty string")
    if metric not in FRONTIER_AXES:
        raise EvolveSubmitError(f"metric must be one of {list(FRONTIER_AXES)}")

    # Ledger invariants (incl. non-negative cost/time) must pass before Bene.
    try:
        record = FrontierRecord(
            candidate=candidate.name,
            ladder_id=measured["ladder_id"],
            base_model=measured["base_model"],
            scores=dict(measured["scores"]),
            budget_usd=measured["budget_usd"],
            budget_wall_clock_min=measured["budget_wall_clock_min"],
            receipt=measured["receipt"],
            measured_at_utc=measured["measured_at_utc"],
            promotion=None,
        )
    except ValueError as exc:
        raise EvolveSubmitError(f"invalid frontier record: {exc}") from exc

    if store is None or conn is None:
        if bene_db is None:
            raise EvolveSubmitError("bene database path is required", exit_code=_EXIT_BENE)
        store, conn = open_bene_context(bene_db, agent_id)

    try:
        outcome = bridge_collaborative_candidate(
            candidate,
            ladder_id=measured["ladder_id"],
            scores=measured["scores"],
            baseline=baseline_axes,
            metric=metric,
            store=store,
            conn=conn,
            agent_id=agent_id,
            api=api,
        )
    except EvolveSubmitError:
        raise
    except Exception as exc:  # noqa: BLE001 — Bene boundary; never echo exception text
        raise _bene_error("bene bridge error", exc) from None

    if not isinstance(outcome, BridgeOutcome):
        raise EvolveSubmitError("bene bridge returned an unexpected outcome", exit_code=_EXIT_BENE)

    try:
        promotion = PromotionReceipt(
            candidate_engram_id=outcome.candidate_engram_id,
            promoted=_require_bool(outcome.promoted, label="outcome.promoted"),
            status=str(outcome.status),
            verdict_engram=outcome.verdict_engram,
        )
        record = replace(record, promotion=promotion)
    except ValueError as exc:
        raise EvolveSubmitError(
            f"invalid promotion receipt from bene ({type(exc).__name__})",
            exit_code=_EXIT_BENE,
        ) from None

    out_path = Path(out)
    _persist_frontier(
        out_path=out_path,
        record=record,
        promotion=promotion,
        generated_at_utc=generated_at_utc,
    )

    return {
        "candidate": candidate.name,
        "ladder_id": measured["ladder_id"],
        "base_model": measured["base_model"],
        "promoted": promotion.promoted,
        "status": promotion.status,
        "candidate_engram_id": promotion.candidate_engram_id,
        "verdict_engram": promotion.verdict_engram,
        "reason": outcome.reason,
        "frontier": str(out_path),
    }


def cmd_evolve_submit(args: argparse.Namespace) -> int:
    try:
        summary = submit_measured_candidate(
            agent=args.agent,
            measurement=args.measurement,
            baseline=args.baseline,
            metric=args.metric,
            out=args.out,
            agent_id=args.agent_id,
            bene_db=args.bene_db,
        )
    except EvolveSubmitError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(summary, indent=2, sort_keys=True))
    return _EXIT_OK


def register_evolve_submit_parser(subs: argparse._SubParsersAction) -> None:
    submit = subs.add_parser(
        "evolve-submit",
        help=(
            "submit an adx measure JSON through the collaborative Bene gate "
            "and export frontier.json"
        ),
    )
    submit.add_argument("--agent", required=True, help="AgentCandidate directory")
    submit.add_argument(
        "--measurement",
        required=True,
        help="path to durable adx measure JSON artifact (not re-measured here)",
    )
    submit.add_argument(
        "--baseline",
        required=True,
        help="baseline frontier axes JSON (raw axes or measure JSON with scores)",
    )
    submit.add_argument("--bene-db", required=True, help="Bene SQLite database path")
    submit.add_argument(
        "--agent-id",
        required=True,
        help="Bene agent_id registered in --bene-db",
    )
    submit.add_argument(
        "--metric",
        required=True,
        choices=list(FRONTIER_AXES),
        help="promotion metric Bene's kill gate evaluates",
    )
    submit.add_argument(
        "--out",
        required=True,
        help="frontier.json output path (atomic export via FrontierLedger)",
    )
    submit.set_defaults(func=cmd_evolve_submit)
