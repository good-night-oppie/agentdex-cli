"""Bounded poke-env ladder windows with battle-backed rating evidence."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LadderWindow:
    rating: float
    battle_tag: str
    opponents: tuple[str, ...]
    wall_clock_sec: float


async def run_ladder_window(player: Any, *, n_games: int, timeout_sec: float) -> LadderWindow:
    """Play rated games, enforce the budget, and always close the PS socket."""
    if n_games <= 0 or timeout_sec <= 0:
        raise ValueError("n_games and timeout_sec must both be > 0")
    started = time.monotonic()
    try:
        await asyncio.wait_for(player.ladder(n_games), timeout=timeout_sec)
        completed = [battle for battle in player.battles.values() if battle.finished]
        rated = [battle for battle in completed if battle.rating is not None]
        if not rated:
            raise RuntimeError("ladder window completed without a server rating")
        latest = rated[-1]
        return LadderWindow(
            rating=float(latest.rating),
            battle_tag=str(latest.battle_tag),
            opponents=tuple(str(b.opponent_username or "") for b in completed),
            wall_clock_sec=max(time.monotonic() - started, 0.0),
        )
    finally:
        try:
            await player.ps_client.stop_listening()
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass
