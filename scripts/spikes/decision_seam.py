"""Spike 2 (ADR-0014 Phase 1): the poke-env DECISION SEAM.

Player.choose_move is the single override point where an agentdex policy — and,
later, a codex-evolved strategy — plugs in. A trivial heuristic (pick the
highest base-power move) should beat RandomPlayer well over 50%, proving (a) the
seam works and (b) win-rate is a clean eval signal for the meta-harness loop.

    scripts/adx_ps_server.sh &
    .venv/bin/python scripts/spikes/decision_seam.py
"""

from __future__ import annotations

import asyncio
import os

from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.player import Player, RandomPlayer

PS_HOST = os.environ.get("ADX_PS_HOST", "localhost")
PS_PORT = os.environ.get("ADX_PS_PORT", "8000")
SERVER = ServerConfiguration(
    f"ws://{PS_HOST}:{PS_PORT}/showdown/websocket",
    "https://play.pokemonshowdown.com/action.php?",
)


class MaxBasePowerPlayer(Player):
    """The seam: override choose_move. A codex/BENE-evolved policy slots in here
    with the same signature and a smarter body."""

    def choose_move(self, battle):
        if battle.available_moves:
            best = max(battle.available_moves, key=lambda m: m.base_power)
            return self.create_order(best)
        return self.choose_random_move(battle)


async def main() -> int:
    """Run the spike; return a shell exit code (0 pass, 1 regression).

    This script IS the Phase-1 proof that win-rate is an eval signal, so a
    sub-threshold result must surface as a non-zero exit — otherwise a smoke/CI
    wrapper records a failed threshold as success.
    """
    n = int(os.environ.get("ADX_SPIKE_N", "10"))
    heuristic = MaxBasePowerPlayer(
        account_configuration=AccountConfiguration("adx-maxbp", None),
        server_configuration=SERVER,
        battle_format="gen9randombattle",
        max_concurrent_battles=1,
    )
    rng = RandomPlayer(
        account_configuration=AccountConfiguration("adx-rng", None),
        server_configuration=SERVER,
        battle_format="gen9randombattle",
        max_concurrent_battles=1,
    )
    await heuristic.battle_against(rng, n_battles=n)
    wr = heuristic.n_won_battles / n
    print(
        f"[spike2] MaxBasePower vs Random over {n}: won {heuristic.n_won_battles} (win-rate {wr:.0%})"
    )
    if wr > 0.5:
        print("[spike2] OK — decision seam works; win-rate is a usable eval signal")
        return 0
    print(
        f"[spike2] FAIL — heuristic did not dominate (win-rate {wr:.0%} <= 50%); "
        "raise ADX_SPIKE_N if this is variance, else the decision seam regressed"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
