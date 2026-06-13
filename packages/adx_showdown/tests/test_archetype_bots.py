from __future__ import annotations

import asyncio

import pytest
from adx_showdown.bots import balance_bot, hyper_offense_bot, max_damage_bot, random_bot, stall_bot
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.sim import run_battle

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def test_balance_bot_runs_to_completion():
    """Balance archetype gym bot completes gen9randombattle without errors."""

    async def _run():
        async with Sidecar() as sc:
            result = await run_battle(
                sc,
                battle_id="test-balance-bot",
                format_id="gen9randombattle",
                p1_name="BalancePlayer",
                p2_name="RandomPlayer",
                p1_policy=balance_bot(sc, fallback_seed=101),
                p2_policy=random_bot(102),
                seed=[101, 102, 103, 104],
            )
            assert result.winner in ("BalancePlayer", "RandomPlayer")

    asyncio.run(_run())


def test_hyper_offense_bot_runs_to_completion():
    """Hyper-offense archetype gym bot completes gen9randombattle without errors."""

    async def _run():
        async with Sidecar() as sc:
            result = await run_battle(
                sc,
                battle_id="test-hyper-offense-bot",
                format_id="gen9randombattle",
                p1_name="HyperPlayer",
                p2_name="MaxDmgPlayer",
                p1_policy=hyper_offense_bot(sc, fallback_seed=201),
                p2_policy=max_damage_bot(sc, fallback_seed=202),
                seed=[201, 202, 203, 204],
            )
            assert result.winner in ("HyperPlayer", "MaxDmgPlayer")

    asyncio.run(_run())


def test_stall_bot_runs_to_completion():
    """Stall archetype gym bot completes gen9randombattle without errors."""

    async def _run():
        async with Sidecar() as sc:
            result = await run_battle(
                sc,
                battle_id="test-stall-bot",
                format_id="gen9randombattle",
                p1_name="StallPlayer",
                p2_name="BalancePlayer",
                p1_policy=stall_bot(sc, fallback_seed=301),
                p2_policy=balance_bot(sc, fallback_seed=302),
                seed=[301, 302, 303, 304],
            )
            assert result.winner in ("StallPlayer", "BalancePlayer")

    asyncio.run(_run())
