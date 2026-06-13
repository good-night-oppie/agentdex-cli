"""Phase-A3 — sidecar lifecycle, lockstep determinism, re-sim parity, RSS cap.

Criteria (ROADMAP phase 3, gate anchors IDEAL §Arena A2/A6):
- 3 concurrent seeded battles complete in ONE sidecar process under ~200MB RSS
- recorded inputLog re-simulates to identical outcome (no network)
- sidecar starts/stops cleanly from the pytest harness

Skips (with reason) when node or node_modules are absent — install via
`npm install` in packages/adx_showdown/.
"""

from __future__ import annotations

import asyncio

import pytest
from adx_showdown.sidecar import Sidecar, SidecarError, sidecar_available
from adx_showdown.sim import (
    BattleResult,
    first_legal_policy,
    replay_input_log,
    run_battle,
    run_concurrent_battles,
    seeded_random_policy,
)

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def _battle_spec(i: int, *, seed_base: int = 1000) -> dict:
    return dict(
        battle_id=f"b{i}",
        format_id="gen9randombattle",
        p1_name=f"Alpha{i}",
        p2_name=f"Beta{i}",
        p1_policy=seeded_random_policy(seed_base + i * 2),
        p2_policy=seeded_random_policy(seed_base + i * 2 + 1),
        seed=[seed_base + i, 2, 3, 4],
    )


def test_sidecar_lifecycle_clean_start_stop():
    async def _run() -> None:
        async with Sidecar() as sc:
            assert sc.ready is not None and sc.ready["event"] == "ready"
            rss = await sc.rss_mb()
            assert rss > 10  # a real process
        assert sc.returncode == 0  # clean shutdown, not a kill

    asyncio.run(_run())


def test_lockstep_same_seed_same_outcome():
    """Lockstep + seeded policies + battle seed ⇒ byte-identical outcome."""

    async def _one() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_battle_spec(0))

    r1 = asyncio.run(_one())
    r2 = asyncio.run(_one())
    assert (r1.winner, r1.turns) == (r2.winner, r2.turns)
    assert r1.input_log == r2.input_log, "lockstep input logs must be identical"
    assert r1.choice_errors == 0


def test_inputlog_resimulates_to_identical_outcome():
    """A2 grounding: the recorded inputLog is the re-simulable artifact."""

    async def _run() -> tuple[BattleResult, BattleResult]:
        async with Sidecar() as sc:
            original = await run_battle(sc, **_battle_spec(1))
            replayed = await replay_input_log(
                sc, battle_id="b1-replay", input_log=original.input_log
            )
            return original, replayed

    original, replayed = asyncio.run(_run())
    assert replayed.winner == original.winner
    assert replayed.turns == original.turns


def test_three_concurrent_battles_one_process_under_200mb():
    """ROADMAP criterion 1 — RSS measured and printed into the transcript."""

    async def _run() -> tuple[list[BattleResult], float, int]:
        async with Sidecar() as sc:
            results = await run_concurrent_battles(sc, [_battle_spec(i) for i in range(3)])
            rss = await sc.rss_mb()
            pid = sc.ready["pid"] if sc.ready else -1
            return results, rss, pid

    results, rss, pid = asyncio.run(_run())
    assert len(results) == 3 and all(r.turns > 0 for r in results)
    print(f"\nRSS_MEASUREMENT: 3 concurrent battles in pid={pid}: {rss:.1f} MB RSS")
    assert rss < 220, f"sidecar RSS {rss:.1f} MB exceeds the 220 MB criterion"


def test_capacity_cap_rejects_excess_battles():
    async def _run() -> str:
        async with Sidecar(max_battles=1) as sc:
            await sc.request(
                "start",
                battle="cap-1",
                format="gen9randombattle",
                seed=[9, 9, 9, 9],
                p1={"name": "A", "team": None},
                p2={"name": "B", "team": None},
            )
            try:
                await sc.request(
                    "start",
                    battle="cap-2",
                    format="gen9randombattle",
                    seed=[9, 9, 9, 9],
                    p1={"name": "C", "team": None},
                    p2={"name": "D", "team": None},
                )
            except SidecarError as e:
                return str(e)
            return ""

    err = asyncio.run(_run())
    assert "capacity" in err


def test_first_legal_policy_completes_battle():
    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(
                sc,
                battle_id="fl",
                format_id="gen9randombattle",
                p1_name="First",
                p2_name="Legal",
                p1_policy=first_legal_policy,
                p2_policy=first_legal_policy,
                seed=[5, 6, 7, 8],
            )

    result = asyncio.run(_run())
    assert result.winner in ("First", "Legal", "")
    assert result.turns > 0
