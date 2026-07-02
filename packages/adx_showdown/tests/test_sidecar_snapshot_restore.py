"""Regression coverage for the sidecar snapshot/restore contract.

These tests intentionally exercise the real Node sidecar rather than a fake: the
contract depends on Pokemon Showdown engine serialization, sidecar mirror state,
and the existing inputLog replay rail all staying aligned.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from adx_showdown.protocol import legal_choices, parse_request
from adx_showdown.sidecar import Sidecar, SidecarError, sidecar_available
from adx_showdown.sim import _fallback_choice, replay_input_log

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def _player(name: str, seed0: int) -> dict[str, Any]:
    return {"name": name, "team": None, "seed": [seed0, 2, 3, 4]}


async def _start_battle(sc: Sidecar, battle: str = "snap-battle") -> dict[str, Any]:
    resp = await sc.request(
        "start",
        battle=battle,
        format="gen9randombattle",
        seed=[100, 2, 3, 4],
        p1=_player("SnapA", 101),
        p2=_player("SnapB", 102),
    )
    return resp["state"]


def _choices_from_state(
    state: dict[str, Any], last_req: dict[str, Any] | None = None
) -> tuple[dict[str, str], dict[str, Any]]:
    """Pick deterministic legal choices for every currently pending side."""

    last_req = dict(last_req or {})
    choices: dict[str, str] = {}
    for err in state.get("errors", []):
        side = err.get("side", "")
        retry = _fallback_choice(last_req.get(side), err.get("error", ""))
        if side and retry is not None:
            choices[side] = retry
    for side, raw in (state.get("pending") or {}).items():
        if raw is None or side in choices:
            continue
        req = parse_request(raw)
        last_req[side] = req
        legal = legal_choices(req)
        if legal:
            choices[side] = legal[0]
    return choices, last_req


async def _advance_one_turn(sc: Sidecar, battle: str, state: dict[str, Any]) -> dict[str, Any]:
    choices, _ = _choices_from_state(state)
    assert choices, f"expected pending choices before snapshot, got state={state!r}"
    resp = await sc.request("step", battle=battle, choices=choices)
    return resp["state"]


async def _finish_from_state(
    sc: Sidecar,
    battle: str,
    state: dict[str, Any],
    *,
    max_steps: int = 500,
) -> dict[str, Any]:
    last_req: dict[str, Any] = {}
    for _ in range(max_steps):
        if state.get("end"):
            return state
        choices, last_req = _choices_from_state(state, last_req)
        assert choices, f"battle stalled after restore at turn {state.get('turns')}: {state!r}"
        resp = await sc.request("step", battle=battle, choices=choices)
        state = resp["state"]
    raise AssertionError(f"battle did not finish within {max_steps} post-restore steps")


async def _snapshot_after_one_turn(
    sc: Sidecar,
    battle: str = "snap-battle",
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = await _start_battle(sc, battle)
    state = await _advance_one_turn(sc, battle, state)
    resp = await sc.request("snapshot", battle=battle)
    return resp, state


def test_snapshot_returns_versioned_engine_state_and_input_log() -> None:
    async def _run() -> None:
        async with Sidecar() as sc:
            resp, state_before_snapshot = await _snapshot_after_one_turn(sc)
            snapshot = resp["snapshot"]

            assert resp["battle"] == "snap-battle"
            assert resp["active"] == 1
            assert snapshot["version"] == 1
            assert snapshot["engine"] == "pokemon-showdown"
            assert snapshot["formatid"] == "gen9randombattle"
            assert isinstance(snapshot["battle_state"], dict)
            assert snapshot["inputLog"][:3] == [
                '>start {"formatid":"gen9randombattle","seed":[100,2,3,4]}',
                '>player p1 {"name":"SnapA","seed":[101,2,3,4]}',
                '>player p2 {"name":"SnapB","seed":[102,2,3,4]}',
            ]
            assert len(snapshot["inputLog"]) > 3
            assert snapshot["sidecar"]["turns"] == snapshot["turns"]
            assert snapshot["sidecar"]["pending"].keys() == {"p1", "p2"}
            assert resp["state"]["turns"] == state_before_snapshot["turns"]
            assert resp["state"]["end"] is None

    asyncio.run(_run())


def test_restore_replaces_live_battle_and_continues_to_replayable_end() -> None:
    async def _run() -> None:
        async with Sidecar() as sc:
            snap_resp, _ = await _snapshot_after_one_turn(sc, battle="replace-live")
            restore = await sc.request(
                "restore",
                battle="replace-live",
                snapshot=snap_resp["snapshot"],
                replace=True,
            )

            assert restore["restored"] is True
            assert restore["replaced"] is True
            assert restore["battle"] == "replace-live"
            final_state = await _finish_from_state(sc, "replace-live", restore["state"])
            replayed = await replay_input_log(
                sc,
                battle_id="replace-live-replay",
                input_log=final_state["end"]["inputLog"],
            )
            assert replayed.winner == final_state["end"]["winner"]
            assert replayed.turns == final_state["end"]["turns"]
            assert (
                final_state["end"]["inputLog"][: len(snap_resp["snapshot"]["inputLog"])]
                == snap_resp["snapshot"]["inputLog"]
            )

    asyncio.run(_run())


def test_restore_after_sidecar_restart_continues_in_flight_battle() -> None:
    async def _run() -> None:
        async with Sidecar() as sc:
            snap_resp, _ = await _snapshot_after_one_turn(sc, battle="restart-live")
            snapshot = snap_resp["snapshot"]

        async with Sidecar() as restarted:
            restore = await restarted.request(
                "restore",
                battle="restart-live",
                snapshot=snapshot,
            )
            assert restore["restored"] is True
            assert restore["replaced"] is False
            final_state = await _finish_from_state(restarted, "restart-live", restore["state"])
            replayed = await replay_input_log(
                restarted,
                battle_id="restart-live-replay",
                input_log=final_state["end"]["inputLog"],
            )
            assert replayed.winner == final_state["end"]["winner"]
            assert replayed.turns == final_state["end"]["turns"]

    asyncio.run(_run())


def test_restore_rejects_malformed_snapshot_without_creating_battle() -> None:
    async def _run() -> None:
        async with Sidecar() as sc:
            await _start_battle(sc, battle="control")
            with pytest.raises(SidecarError, match="unsupported snapshot version"):
                await sc.request(
                    "restore",
                    battle="bad-version",
                    snapshot={"version": 999, "battle_state": {}, "inputLog": [], "sidecar": {}},
                )
            with pytest.raises(SidecarError, match="missing battle_state"):
                await sc.request(
                    "restore",
                    battle="missing-state",
                    snapshot={"version": 1, "inputLog": [], "sidecar": {}},
                )
            with pytest.raises(SidecarError, match="not owned|no battle"):
                await sc.request("step", battle="bad-version", choices={"p1": "move 1"})
            await sc.request("step", battle="control", choices={})

    asyncio.run(_run())


def test_restore_without_replace_cannot_overwrite_active_battle() -> None:
    async def _run() -> None:
        async with Sidecar() as sc:
            snap_resp, _ = await _snapshot_after_one_turn(sc, battle="permission-source")
            await _start_battle(sc, battle="permission-target")
            with pytest.raises(SidecarError, match="already active"):
                await sc.request(
                    "restore",
                    battle="permission-target",
                    snapshot=snap_resp["snapshot"],
                )
            # The failed restore must leave the live target battle usable.
            state = await sc.request("snapshot", battle="permission-target")
            assert state["battle"] == "permission-target"

    asyncio.run(_run())
