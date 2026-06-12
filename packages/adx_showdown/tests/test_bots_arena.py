"""Phase-A4 — anchor bots sanity + battle-as-expedition integration.

Criteria (ROADMAP phase 4, gate anchors A2/A4):
- max-damage beats random in ≥70% of 50 seeded battles (anchor ordering)
- one seeded battle through run_expedition_orchestrator emits the full card
  bundle on disk + a KAOS lineage row
- Pareto pool includes battle cards (no excluded-failed from None cost)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml
from adx_showdown.arena_bridge import ScriptedBattleBridge
from adx_showdown.bots import max_damage_bot, random_bot
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.sim import run_battle

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


@pytest.mark.timeout(600)
def test_max_damage_beats_random_anchor_ordering():
    """ROADMAP criterion 3 — win rate printed into the transcript."""
    N = 50

    async def _run() -> float:
        wins = 0
        async with Sidecar() as sc:
            for i in range(N):
                result = await run_battle(
                    sc,
                    battle_id=f"anchor-{i}",
                    format_id="gen9randombattle",
                    p1_name="MaxDmg",
                    p2_name="Rando",
                    p1_policy=max_damage_bot(sc, fallback_seed=9000 + i),
                    p2_policy=random_bot(5000 + i),
                    seed=[3000 + i, 11, 22, 33],
                )
                wins += result.winner == "MaxDmg"
        return wins / N

    win_rate = asyncio.run(_run())
    print(f"\nANCHOR_ORDERING: max-damage vs random win rate = {win_rate:.2f} over {N} battles")
    assert win_rate >= 0.70, f"max-damage win rate {win_rate:.2f} < 0.70 anchor criterion"


def test_battle_expedition_full_card_bundle_and_kaos_row(tmp_path: Path):
    """ROADMAP criteria 1+2 — battle = expedition variant, end to end."""
    from agentdex_engine.cards import TaskCard
    from agentdex_engine.expedition import run_expedition_orchestrator
    from agentdex_engine.oracle import BattleOracle, OracleChain
    from agentdex_engine.shared.kaos_adapter import log_expedition_lineage

    spec = {
        "battle_id": "exp-arena-smoke",
        "format": "gen9randombattle",
        "seed": [4242, 1, 2, 3],
        "anchor": "random",
        "anchor_seed": 77,
        "my_team": None,
        "anchor_team": None,
        "expedition_id": "pending",  # orchestrator derives its own id
    }
    task_card = TaskCard(
        id="arena-smoke-battle",
        source_bundle_hash=__import__("hashlib")
        .sha256(json.dumps(spec, sort_keys=True).encode())
        .hexdigest(),
        environment_spec={"format": spec["format"], "anchor": spec["anchor"]},
        oracle_spec_ref="battle",
        budget_token_cap=0,
        budget_dollar_cap=0.0,
        expected_output_kind="trace",
        version="0.1.0",
    )
    arena_dir = tmp_path / "arena"
    bridges = [
        ScriptedBattleBridge("maxdmg", "max_damage", artifacts_dir=arena_dir, policy_seed=1),
        ScriptedBattleBridge("firstrand", "random", artifacts_dir=arena_dir, policy_seed=2),
    ]
    chain = OracleChain({"battle": BattleOracle(audit_rate=0.0)})

    result_cards, verdict, evolution_card, _ = asyncio.run(
        run_expedition_orchestrator(
            task_card,
            bridges,  # type: ignore[arg-type]  # structural _BridgeLike
            chain,
            judge_llm="unused-no-soft-oracle",
            repo_root=tmp_path,
            prompt_override=json.dumps(spec),
        )
    )

    # criterion 2: no excluded-failed from None cost — both cards in the pool
    assert len(result_cards) == 2
    for rc in result_cards:
        assert rc.pareto_position != "excluded-failed", rc
        assert rc.cost_dollar == 0.0

    # criterion 1: full artifact bundle on disk
    exp_dir = tmp_path / "expeditions" / result_cards[0].expedition_id
    exp_dir.mkdir(parents=True)
    (exp_dir / "task_card.yaml").write_text(yaml.safe_dump(task_card.model_dump()))
    for rc in result_cards:
        (exp_dir / f"result_card_{rc.agent_id}.yaml").write_text(yaml.safe_dump(rc.model_dump()))
    (exp_dir / "pareto_verdict.yaml").write_text(yaml.safe_dump(verdict.model_dump()))
    (exp_dir / "evolution_card.yaml").write_text(yaml.safe_dump(evolution_card.model_dump()))
    for name in ("task_card", "pareto_verdict", "evolution_card"):
        assert (exp_dir / f"{name}.yaml").is_file()
    battle_cards = sorted(arena_dir.glob("*.battle_card.json"))
    input_logs = sorted(arena_dir.glob("*.inputlog.json"))
    assert len(battle_cards) == 2 and len(input_logs) == 2
    print(f"\nCARD_BUNDLE: {exp_dir} + {len(battle_cards)} battle cards in {arena_dir}")

    # criterion 1: KAOS lineage row
    kaos_db = tmp_path / "kaos.db"
    agent_id = log_expedition_lineage(
        kaos_db, result_cards[0].expedition_id, evolution_card.model_dump(mode="json")
    )
    assert agent_id, "KAOS lineage row not persisted"
    import sqlite3

    rows = (
        sqlite3.connect(kaos_db)
        .execute("SELECT name FROM agents WHERE agent_id = ?", (agent_id,))
        .fetchall()
    )
    assert rows and rows[0][0].startswith("expedition-")
    print(f"KAOS_ROW: agent_id={agent_id} name={rows[0][0]}")


def test_bridge_report_win_field_matches_winner(tmp_path: Path):
    async def _run():
        bridge = ScriptedBattleBridge("probe", "random", artifacts_dir=tmp_path, policy_seed=3)
        spec = {
            "battle_id": "probe-1",
            "format": "gen9randombattle",
            "seed": [777, 1, 2, 3],
            "anchor": "random",
            "anchor_seed": 8,
        }
        return await bridge.send(json.dumps(spec))

    resp = asyncio.run(_run())
    report = json.loads(resp.text)
    assert report["win"] == (report["winner"] == "probe")
    assert resp.cost_usd == 0.0 and resp.tokens == 0
    assert Path(report["input_log_path"]).is_file()
    assert Path(report["battle_card_path"]).is_file()
