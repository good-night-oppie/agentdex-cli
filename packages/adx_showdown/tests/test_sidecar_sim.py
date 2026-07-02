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
from adx_showdown.protocol import parse_request
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


async def _finish_with_first_legal(sc: Sidecar, battle_id: str, state: dict) -> BattleResult:
    protocol_log = list(state.get("protocol_log") or [])
    for step_n in range(1, 500):
        if state.get("end"):
            return BattleResult(
                battle_id=battle_id,
                winner=state["end"].get("winner") or "",
                turns=int(state["end"].get("turns", 0)),
                input_log=list(state["end"].get("inputLog") or []),
                key_lines=list(state["end"].get("keyLines") or []),
                protocol_log=protocol_log,
                protocol_truncated=bool(state.get("protocol_truncated")),
                steps=step_n - 1,
            )
        choices = {}
        for side, raw in (state.get("pending") or {}).items():
            if raw is not None:
                choice = first_legal_policy(parse_request(raw))
                if choice is not None:
                    choices[side] = choice
        assert choices, f"{battle_id}: no choices at turn {state.get('turns')}"
        resp = await sc.request("step", battle=battle_id, choices=choices)
        state = resp["state"]
        protocol_log.extend(state.get("protocol_log") or [])
    raise AssertionError(f"{battle_id}: did not finish")


def test_snapshot_restore_recovers_in_flight_battle_after_restart():
    async def _run() -> tuple[dict, BattleResult, BattleResult]:
        async with Sidecar() as sc:
            start = await sc.request(
                "start",
                battle="snap",
                format="gen9randombattle",
                seed=[21, 22, 23, 24],
                p1={"name": "SnapA", "team": None, "seed": [22, 22, 23, 24]},
                p2={"name": "SnapB", "team": None, "seed": [23, 22, 23, 24]},
            )
            snap = await sc.request("snapshot", battle="snap")
            assert snap["snapshot"]["version"] == 1
            assert snap["snapshot"]["inputLog"] == [
                line for line in snap["snapshot"]["inputLog"] if line.startswith(">")
            ]
            original = await _finish_with_first_legal(sc, "snap", start["state"])
            assert original.turns > 0

        async with Sidecar() as sc2:
            restored = await sc2.request("restore", battle="snap", snapshot=snap["snapshot"])
            recovered = await _finish_with_first_legal(sc2, "snap", restored["state"])
            replayed = await replay_input_log(
                sc2, battle_id="snap-replay", input_log=recovered.input_log
            )
            return snap, recovered, replayed

    snap, recovered, replayed = asyncio.run(_run())
    assert snap["snapshot"]["battle_state"]["formatid"] == "gen9randombattle"
    assert recovered.turns > snap["snapshot"]["turns"]
    assert replayed.winner == recovered.winner
    assert replayed.turns == recovered.turns


def test_snapshot_restore_fail_safely_for_bad_requests():
    async def _run() -> None:
        async with Sidecar() as sc:
            with pytest.raises(SidecarError, match="snapshot requires battle"):
                await sc.request("snapshot")
            with pytest.raises(SidecarError, match="restore requires snapshot"):
                await sc.request("restore", battle="bad")
            with pytest.raises(SidecarError, match="unsupported snapshot version 999"):
                await sc.request(
                    "restore",
                    battle="bad",
                    snapshot={"version": 999, "engine": "pokemon-showdown", "battle_state": {}},
                )

    asyncio.run(_run())


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
    assert rss < 200, f"sidecar RSS {rss:.1f} MB exceeds the 200 MB criterion"


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
