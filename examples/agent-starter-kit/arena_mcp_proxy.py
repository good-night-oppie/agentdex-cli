"""MCP proxy: exposes ArenaClient as game-only tools to any MCP harness.

Why this exists: the deployed arena's MCP surface requires the agent to pass `token`
+ `battle_id` on every call (per ConsentAuthority scope-checks). This proxy hides
both — the agent only sees `decide_move(choice_index)` style tools. Token + battle_id
are bound at server startup via env.

Run:
    ARENA_TOKEN=... ARENA_BATTLE_ID=... uv run python arena_mcp_proxy.py

Or via stdio in your harness config (see .mcp.json in this dir).
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from arena_client import ArenaClient, DEFAULT_BASE


_BASE = os.environ.get("ARENA_BASE", DEFAULT_BASE)
_TOKEN = os.environ.get("ARENA_TOKEN", "")
_BATTLE = os.environ.get("ARENA_BATTLE_ID", "")

if not _TOKEN:
    raise SystemExit("set ARENA_TOKEN (run bootstrap.sh first)")

_client = ArenaClient(_BASE)
mcp = FastMCP("agentdex-arena-proxy")


@mcp.tool()
def show_state() -> dict[str, Any]:
    """Fetch current battle state via GET /battle/{id}/state. Returns turn, state-text,
    n_choices, foe_active, foe_hp_pct, recent_turns — same shape as decide_move's
    response. If the battle has ended, returns {'status':'ended', ...}."""
    if not _BATTLE:
        return {"error": "no battle bound; set ARENA_BATTLE_ID before starting proxy"}
    return _client.battle_state(_TOKEN, _BATTLE)


@mcp.tool()
def decide_move(choice_index: int) -> dict[str, Any]:
    """Submit a 1-based move index. Returns the new battle state (or {'status':'ended', ...})."""
    return _client.battle_choose(_TOKEN, _BATTLE, choice_index)


@mcp.tool()
def request_evolution(team_packed: str, reasoning: str) -> dict[str, Any]:
    """After a battle, ask the platform for mutation seeds for your team."""
    return _client.evolution_request(_TOKEN, team_packed=team_packed, reasoning=reasoning)


@mcp.tool()
def get_replay(battle_id: str | None = None) -> dict[str, Any]:
    """Fetch a public replay (input_log + signatures). Defaults to the bound battle."""
    return _client.replay(battle_id or _BATTLE)


@mcp.tool()
def get_ladder() -> dict[str, Any]:
    """Current ladder rankings."""
    return _client.ladder()


if __name__ == "__main__":
    mcp.run()
