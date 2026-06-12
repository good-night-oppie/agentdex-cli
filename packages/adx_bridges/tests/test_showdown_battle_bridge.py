"""Phase-A6 — house battler FIC loop (A7 gate anchors).

Criteria:
- 50+-turn battle with turn-30 context == turn-3 context ±10% (flat FIC)
- state renders ≤2,500 tokens on the fixture corpus (real tokenizer)
- a deliberately-stalling decider auto-forfeits within the timer
- a house battle produces a rated event the ladder accepts
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from adx_bridges.showdown_battle_bridge import (
    BudgetExhausted,
    BudgetGuard,
    LlmBattlePolicy,
    parse_decision,
    play_house_battle,
    render_state,
)
from adx_showdown.bots import random_bot
from adx_showdown.sidecar import sidecar_available
from adx_showdown.teams import starter_pack

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))

PROMPTS_CORPUS: list[str] = []  # filled by the long battle, reused by token test


def _fake_decider(script: str = "1"):
    async def _decide(prompt: str) -> tuple[str, dict]:
        PROMPTS_CORPUS.append(prompt)
        return (
            json.dumps({"choice": int(script), "scratchpad": f"plan: keep option {script}"}),
            {"prompt_tokens": 100, "completion_tokens": 20},
        )

    return _decide


async def _packed(team_name: str) -> str:
    from adx_showdown.sidecar import Sidecar
    from adx_showdown.teams import pack_team

    async with Sidecar() as sc:
        return await pack_team(sc, starter_pack()[team_name])


@pytest.mark.timeout(600)
def test_flat_context_over_50_turn_battle(tmp_path: Path):
    """ROADMAP criterion 1 — FIC: context flat from turn 3 to turn 30+."""

    async def _run():
        stall_team = await _packed("03-stall")
        policy = LlmBattlePolicy(
            decider=_fake_decider("1"),
            trajectory_path=tmp_path / "trajectory.jsonl",
            decide_timeout_s=30.0,
            budget=BudgetGuard(max_decisions=2000),
        )
        result = await play_house_battle(
            battle_id="fic-50",
            format_id="gen9ou",
            seed=[91_000, 3, 5, 7],
            policy=policy,
            opponent=random_bot(4242),
            my_team=stall_team,
            opponent_team=stall_team,
        )
        return result, policy

    result, policy = asyncio.run(_run())
    assert result.turns >= 50, f"need a 50+-turn battle for the criterion (got {result.turns})"
    by_turn = policy.prompt_chars_by_turn
    t3 = next(by_turn[t] for t in sorted(by_turn) if t >= 3)
    t30 = next(by_turn[t] for t in sorted(by_turn) if t >= 30)
    drift = abs(t30 - t3) / t3
    print(
        f"\nFLAT_CONTEXT: turns={result.turns} prompt_chars t3={t3} t30={t30} "
        f"drift={drift:.3f} (criterion <=0.10)"
    )
    assert drift <= 0.10, f"context drift {drift:.3f} exceeds ±10%"
    # trajectory.jsonl written, one line per decision
    lines = (tmp_path / "trajectory.jsonl").read_text().splitlines()
    assert len(lines) >= 50
    assert all("prompt_chars" in json.loads(ln) or "timeout" in json.loads(ln) for ln in lines)


def test_state_renders_under_2500_tokens_fixture_corpus():
    """ROADMAP criterion 4 — real tokenizer, not the 4-chars heuristic."""
    import tiktoken

    assert PROMPTS_CORPUS, "long-battle test populates the corpus first"
    enc = tiktoken.get_encoding("cl100k_base")
    worst = max(len(enc.encode(p)) for p in PROMPTS_CORPUS)
    print(f"\nTOKEN_CAP: {len(PROMPTS_CORPUS)} renders, worst = {worst} tokens (cap 2500)")
    assert worst <= 2500


def test_stalling_decider_auto_forfeits_quickly():
    """ROADMAP criterion 2 — the stalling side LOSES within the timer."""

    async def _stall(prompt: str) -> tuple[str, dict]:
        await asyncio.sleep(30)
        return "1", {}

    async def _run():
        policy = LlmBattlePolicy(decider=_stall, decide_timeout_s=0.2)
        return await play_house_battle(
            battle_id="stall-probe",
            format_id="gen9randombattle",
            seed=[92_000, 1, 2, 3],
            policy=policy,
            opponent=random_bot(7),
            my_name="staller",
            opponent_name="anchor",
        )

    import time as _time

    start = _time.monotonic()
    result = asyncio.run(_run())
    elapsed = _time.monotonic() - start
    print(f"\nAUTO_FORFEIT: winner={result.winner!r} in {elapsed:.1f}s")
    assert result.winner == "anchor", "stalling side must lose"
    assert elapsed < 10, f"forfeit took {elapsed:.1f}s — timer rail not engaging"


def test_house_battle_produces_rated_event(tmp_path: Path):
    """ROADMAP criterion 3 — house bridge result flows into the ladder."""
    from agentdex_engine.modules.arena import EventLog, RatingEvent, recompute_ladder

    async def _run():
        policy = LlmBattlePolicy(decider=_fake_decider("1"), decide_timeout_s=30.0)
        return await play_house_battle(
            battle_id="rated-1",
            format_id="gen9randombattle",
            seed=[93_000, 1, 2, 3],
            policy=policy,
            opponent=random_bot(99),
            my_name="house-flash",
            opponent_name="anchor-random",
        )

    result = asyncio.run(_run())
    events = tmp_path / "events.jsonl"
    elog = EventLog(events)
    elog.append("register", {"name": "house-flash"})
    elog.append("register", {"name": "anchor-random", "frozen": True})
    elog.append(
        "period",
        {
            "events": [
                RatingEvent(
                    battle_id=result.battle_id,
                    p1="house-flash",
                    p2="anchor-random",
                    winner=result.winner,
                    input_log_blake2b16=hashlib.blake2b(
                        "\n".join(result.input_log).encode(), digest_size=16
                    ).hexdigest(),
                ).model_dump()
            ]
        },
    )
    ladder = recompute_ladder(events)
    house = ladder.rating("house-flash")
    assert house.games == 1 and house.rating != 1500.0
    print(
        f"\nRATED_EVENT: battle={result.battle_id} house-flash -> {house.rating:.1f}±{house.rd:.0f}"
    )


def test_parse_decision_tolerant_and_bounded():
    idx, pad = parse_decision('{"choice": 2, "scratchpad": "' + "x" * 5000 + '"}', 4)
    assert idx == 2 and pad is not None and len(pad) <= 1200
    assert parse_decision("I pick 3", 4) == (3, None)
    assert parse_decision("garbage", 4) == (None, None)
    assert parse_decision('{"choice": 9}', 4) == (None, "")


def test_budget_guard_fail_closed():
    guard = BudgetGuard(max_decisions=1)
    guard.spend()
    with pytest.raises(BudgetExhausted):
        guard.spend()


def test_render_state_hard_cap():
    from adx_showdown.protocol import parse_request
    from adx_showdown.sim import BattleContext

    req = parse_request(
        {
            "active": [{"moves": [{"id": "tackle", "move": "T" * 4000, "pp": 1, "maxpp": 1}]}],
            "side": {"id": "p1", "pokemon": []},
        }
    )
    text = render_state(
        req,
        BattleContext(side="p1", turns=1),
        scratchpad="s" * 99_999,
        recent_turns=["r" * 9_999] * 3,
    )
    assert len(text) <= 8_000
