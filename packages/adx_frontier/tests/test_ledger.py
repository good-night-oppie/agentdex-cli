from __future__ import annotations

import json

import pytest
from adx_frontier.ledger import (
    FrontierLedger,
    FrontierRecord,
    PromotionReceipt,
    TrustReceipt,
)


def _record(candidate: str, quality: float, cost: float, wall: float, *, model="model"):
    return FrontierRecord(
        candidate=candidate,
        ladder_id="pokeagent-gen1ou",
        base_model=model,
        scores={"quality": quality, "cost_dollar": cost, "wall_clock_sec": wall},
        budget_usd=5,
        budget_wall_clock_min=10,
        receipt=TrustReceipt("verified", "pokeagent_rating", ref=f"rating:{candidate}"),
        measured_at_utc="2026-07-11T00:00:00Z",
        promotion=PromotionReceipt("engram-1", True, "ACCEPT", "verdict-1"),
    )


def test_frontier_excludes_dominated_records_within_partition() -> None:
    ledger = FrontierLedger(
        [
            _record("best", 1500, 1, 2),
            _record("dominated", 1400, 2, 3),
            _record("tradeoff", 1600, 3, 4),
            _record("other-model", 1, 1, 1, model="other"),
        ]
    )
    assert [r.candidate for r in ledger.frontier("pokeagent-gen1ou", "model")] == [
        "tradeoff",
        "best",
    ]
    assert [r.candidate for r in ledger.frontier("pokeagent-gen1ou", "other")] == ["other-model"]


def test_export_carries_trust_and_accept_promotion_receipts(tmp_path) -> None:
    target = FrontierLedger([_record("best", 1500, 1, 2)]).export(
        tmp_path / "frontier.json", generated_at_utc="2026-07-11T00:00:00Z"
    )
    payload = json.loads(target.read_text())
    entry = payload["partitions"][0]["frontier"][0]
    assert payload["schema_version"] == 1
    assert entry["receipt"]["tier"] == "verified"
    assert entry["promotion"]["status"] == "ACCEPT" and entry["promotion"]["promoted"]


def test_trust_and_promotion_invariants_fail_closed() -> None:
    with pytest.raises(ValueError, match="raw artifacts"):
        TrustReceipt("self_reported", "raw_artifacts")
    with pytest.raises(ValueError, match="exactly for ACCEPT"):
        PromotionReceipt("engram", True, "REJECT", "verdict")
