"""Spike 1 (ADR-0014 Phase 1): poke-env drives battles on OUR PS server.

Proves the substrate end-to-end with zero gateway coupling: two RandomPlayers
connect to a locally-booted Pokémon Showdown server and complete gen9randombattles.

    pip/uv pip install poke-env       # if not already in the env
    scripts/adx_ps_server.sh &        # boot the vendored PS server on :8000
    .venv/bin/python scripts/spikes/two_random_players.py

Point at the box later with ADX_PS_HOST=54.203.252.69.
"""

from __future__ import annotations

import asyncio
import os

from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.player import RandomPlayer

PS_HOST = os.environ.get("ADX_PS_HOST", "localhost")
PS_PORT = os.environ.get("ADX_PS_PORT", "8000")
SERVER = ServerConfiguration(
    f"ws://{PS_HOST}:{PS_PORT}/showdown/websocket",
    "https://play.pokemonshowdown.com/action.php?",
)


async def main() -> None:
    n = 2
    p1 = RandomPlayer(
        account_configuration=AccountConfiguration("adx-rand-1", None),
        server_configuration=SERVER,
        battle_format="gen9randombattle",
        max_concurrent_battles=1,
    )
    p2 = RandomPlayer(
        account_configuration=AccountConfiguration("adx-rand-2", None),
        server_configuration=SERVER,
        battle_format="gen9randombattle",
        max_concurrent_battles=1,
    )
    await p1.battle_against(p2, n_battles=n)
    print(f"[spike1] server={SERVER.websocket_url}")
    print(f"[spike1] {n} gen9randombattle(s): p1 won {p1.n_won_battles}, p2 won {p2.n_won_battles}")
    ok = (p1.n_won_battles + p2.n_won_battles) >= 1
    print("[spike1] OK — poke-env drives battles on our PS server" if ok else "[spike1] FAIL")


if __name__ == "__main__":
    asyncio.run(main())
