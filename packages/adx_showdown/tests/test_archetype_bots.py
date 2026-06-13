from __future__ import annotations

import asyncio

import pytest
from adx_showdown.bots import balance_bot, random_bot
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
