"""Phase-A4 — BattleCard schema + BattleOracle verdicts (A2/A4 gate anchors)."""

from __future__ import annotations

import json

import pytest
from agentdex_engine.cards import BattleCard, TaskCard
from agentdex_engine.oracle import BattleOracle
from pydantic import ValidationError

TASK = TaskCard(
    id="arena-smoke",
    source_bundle_hash="0" * 64,
    environment_spec={"format": "gen9randombattle"},
    oracle_spec_ref="battle",
    budget_token_cap=0,
    budget_dollar_cap=0.0,
    expected_output_kind="trace",
    version="0.1.0",
)


def _card_kwargs(**over):
    base = dict(
        battle_id="b1",
        expedition_id="exp1",
        format_id="gen9ou",
        seed=[1, 2, 3, 4],
        p1_name="Alpha",
        p2_name="Beta",
        winner="Alpha",
        turns=42,
        input_log_path="expeditions/exp1/arena/b1.inputlog.json",
        input_log_blake2b16="ab" * 16,
        duration_sec=1.5,
        decision_tokens=0,
    )
    base.update(over)
    return base


def test_battle_card_roundtrip_and_defaults():
    card = BattleCard(**_card_kwargs())
    assert card.rating_before is None and card.rating_after is None
    assert card.choice_errors == 0
    assert BattleCard.model_validate(card.model_dump()) == card


def test_battle_card_rejects_extra_fields():
    with pytest.raises(ValidationError):
        BattleCard(**_card_kwargs(), smuggled="x")


def test_battle_card_rejects_bad_seed_and_hash():
    with pytest.raises(ValidationError):
        BattleCard(**_card_kwargs(seed=[1, 2, 3]))
    with pytest.raises(ValidationError):
        BattleCard(**_card_kwargs(input_log_blake2b16="not-hex"))


def _report(**over):
    base = dict(
        battle_id="b1",
        me="Alpha",
        opponent="Beta",
        winner="Alpha",
        win=True,
        turns=42,
        input_log_path="/tmp/b1.json",
        format="gen9ou",
        seed=[1, 2, 3, 4],
    )
    base.update(over)
    return json.dumps(base)


def test_oracle_win_and_loss_verdicts():
    win = BattleOracle(audit_rate=0.0).evaluate(_report(), TASK)
    assert win["battle.win"].pass_ and win["battle.win"].score == 1.0
    loss = BattleOracle(audit_rate=0.0).evaluate(_report(winner="Beta", win=False), TASK)
    assert not loss["battle.win"].pass_ and loss["battle.win"].score == 0.0


def test_oracle_unparseable_report_fails_closed():
    v = BattleOracle(audit_rate=0.0).evaluate("not json {", TASK)
    assert not v["battle.win"].pass_
    assert "unparseable" in v["battle.win"].evidence


def test_oracle_dispute_forces_audit_and_falsified_report_fails():
    calls: list[str] = []

    def fake_resim(path: str) -> str:
        calls.append(path)
        return "Beta"  # contradicts reported winner Alpha

    v = BattleOracle(audit_rate=0.0, resim=fake_resim).evaluate(_report(dispute=True), TASK)
    assert calls == ["/tmp/b1.json"]
    assert not v["battle.resim_audit"].pass_
    assert not v["battle.win"].pass_, "falsified report must fail the win verdict"


def test_oracle_audit_confirms_honest_report():
    v = BattleOracle(audit_rate=1.0, resim=lambda p: "Alpha").evaluate(_report(), TASK)
    assert v["battle.resim_audit"].pass_
    assert v["battle.win"].pass_


def test_oracle_audit_sampling_is_deterministic():
    from agentdex_engine.oracle.battle import _audit_sampled

    ids = [f"battle-{i}" for i in range(2000)]
    first = [_audit_sampled(b, 0.10) for b in ids]
    second = [_audit_sampled(b, 0.10) for b in ids]
    assert first == second
    rate = sum(first) / len(first)
    assert 0.06 < rate < 0.14, f"10% sampling out of tolerance: {rate}"


def test_oracle_resim_error_does_not_flip_win():
    def broken(path: str) -> str:
        raise OSError("inputlog missing")

    v = BattleOracle(audit_rate=1.0, resim=broken).evaluate(_report(), TASK)
    assert v["battle.win"].pass_, "audit infra failure must not become a battle loss"
    assert not v["battle.resim_audit"].pass_
    assert v["battle.resim_audit"].uncertainty == 1.0
