"""Partitioned Pareto ledger and deterministic ``frontier.json`` export."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adx_frontier.candidate import FRONTIER_AXES


@dataclass(frozen=True)
class TrustReceipt:
    tier: str
    kind: str
    ref: str = ""
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.tier not in {"verified", "self_reported"}:
            raise ValueError("receipt tier must be verified or self_reported")
        if self.tier == "verified" and (not self.kind or not self.ref):
            raise ValueError("verified receipts require kind and ref")
        if self.tier == "self_reported" and not self.artifacts:
            raise ValueError("self_reported receipts require raw artifacts")


@dataclass(frozen=True)
class PromotionReceipt:
    candidate_engram_id: str
    promoted: bool
    status: str
    verdict_engram: str | None

    def __post_init__(self) -> None:
        if self.promoted != (self.status == "ACCEPT"):
            raise ValueError("promotion must be true exactly for ACCEPT")


@dataclass(frozen=True)
class FrontierRecord:
    candidate: str
    ladder_id: str
    base_model: str
    scores: dict[str, float]
    budget_usd: float
    budget_wall_clock_min: float
    receipt: TrustReceipt
    measured_at_utc: str
    promotion: PromotionReceipt | None = None

    def __post_init__(self) -> None:
        missing = [axis for axis in FRONTIER_AXES if axis not in self.scores]
        extra = [axis for axis in self.scores if axis not in FRONTIER_AXES]
        if missing or extra:
            raise ValueError(f"scores must match frontier axes; missing={missing}, extra={extra}")
        numbers = [*self.scores.values(), self.budget_usd, self.budget_wall_clock_min]
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in numbers):
            raise ValueError("scores and budgets must be finite numbers")
        if self.scores["cost_dollar"] < 0 or self.scores["wall_clock_sec"] < 0:
            raise ValueError("cost and wall-clock scores must be non-negative")
        if self.budget_usd <= 0 or self.budget_wall_clock_min <= 0:
            raise ValueError("budgets must be > 0")
        if not all((self.candidate, self.ladder_id, self.base_model, self.measured_at_utc)):
            raise ValueError("candidate, partition keys, and measured_at_utc are required")

    @property
    def partition(self) -> tuple[str, str]:
        return self.ladder_id, self.base_model


def dominates(left: FrontierRecord, right: FrontierRecord) -> bool:
    if left.partition != right.partition:
        return False
    left_scores, right_scores = left.scores, right.scores
    no_worse = (
        left_scores["quality"] >= right_scores["quality"]
        and left_scores["cost_dollar"] <= right_scores["cost_dollar"]
        and left_scores["wall_clock_sec"] <= right_scores["wall_clock_sec"]
    )
    strict = (
        left_scores["quality"] > right_scores["quality"]
        or left_scores["cost_dollar"] < right_scores["cost_dollar"]
        or left_scores["wall_clock_sec"] < right_scores["wall_clock_sec"]
    )
    return no_worse and strict


class FrontierLedger:
    def __init__(self, records: list[FrontierRecord] | None = None) -> None:
        self._records = list(records or [])

    def add(self, record: FrontierRecord) -> None:
        self._records.append(record)

    def frontier(self, ladder_id: str, base_model: str) -> tuple[FrontierRecord, ...]:
        partition = [r for r in self._records if r.partition == (ladder_id, base_model)]
        return tuple(
            sorted(
                (
                    record
                    for record in partition
                    if not any(dominates(other, record) for other in partition)
                ),
                key=lambda r: (-r.scores["quality"], r.scores["cost_dollar"], r.candidate),
            )
        )

    def export(self, path: str | Path, *, generated_at_utc: str | None = None) -> Path:
        target = Path(path)
        partitions = sorted({record.partition for record in self._records})
        payload: dict[str, Any] = {
            "schema_version": 1,
            "generated_at_utc": generated_at_utc
            or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "partitions": [
                {
                    "ladder_id": ladder,
                    "base_model": model,
                    "frontier": [_record_dict(record) for record in self.frontier(ladder, model)],
                }
                for ladder, model in partitions
            ],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(target)
        return target


def _record_dict(record: FrontierRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["receipt"]["artifacts"] = list(record.receipt.artifacts)
    return payload
