"""MCP surface — streamable-HTTP MCP server (A8).

Exposes tools for visiting agents to interact with the Pokémon Showdown arena
without requiring permanent WebSockets or SSE connections, keeping it lightweight
and sleeping-tolerant.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from adx_showdown.protocol import legal_choices, sanitize_name
from agentdex_arena.consent import ConsentError
from agentdex_arena.gateway import ArenaGateway
from agentdex_arena.offered_seeds import offer_seeds
from agentdex_engine.modules.arena import recompute_ladder

logger = logging.getLogger(__name__)

mcp = FastMCP("agentdex-arena")
mcp.settings.streamable_http_path = "/"
mcp.settings.json_response = True
mcp.settings.stateless_http = True
mcp.settings.transport_security.enable_dns_rebinding_protection = False

# Global references set at runtime
_gateway: ArenaGateway | None = None
_sidecar_fn: Any = None


def get_mcp_app(gateway: ArenaGateway) -> FastMCP:
    global _gateway
    _gateway = gateway
    return mcp


def init_mcp(gateway: ArenaGateway, sidecar_fn: Any) -> None:
    global _gateway, _sidecar_fn
    _gateway = gateway
    _sidecar_fn = sidecar_fn


@mcp.tool()
async def get_battle_state(token: str, battle_id: str) -> dict[str, Any]:
    """Get the current state of a battle session. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    session = _gateway.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    _gateway._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.pending is None:
        raise ValueError("No pending request in session")

    if session.last_state is None:
        raise ValueError("No state available to render")

    return _gateway._render(session, session.last_state)


@mcp.tool()
async def choose_action(token: str, battle_id: str, choice_index: int) -> dict[str, Any]:
    """Choose an action in a battle session by index. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    session = _gateway.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    _gateway._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.pending is None:
        raise ValueError("No pending request in session")

    choices = legal_choices(session.pending)
    if not 1 <= choice_index <= len(choices):
        raise ValueError(f"Choice index out of range 1..{len(choices)}")

    choice = choices[choice_index - 1]
    session.visitor_choices.append(choice)

    from agentdex_arena.gateway import _choice_label, _push_recent

    label = _choice_label(choice, session.pending)
    _push_recent(session, f"T{session.turns}: you → {label}")

    _gateway.events.append(
        "battle",
        {
            "tenant_id": session.claims_token_id,
            "battle_id": battle_id,
            "turn": session.turns,
            "choice": choice,
            "choice_label": label,
            "foe_hp_pct": session.foe_hp_pct,
        },
    )
    session.pending = None
    session.last_touch = _gateway.now()

    if _sidecar_fn is None:
        raise ValueError("Sidecar factory not registered")

    try:
        sidecar = await _sidecar_fn()
        resp = await sidecar.request(
            "step", battle=battle_id, choices={session.visitor_side: choice}
        )
        return await _gateway._advance(session, resp["state"], visitor_choice=None)
    except Exception as e:
        raise ValueError(f"Battle step error: {e}") from None


@mcp.tool()
async def read_scratchpad(token: str, battle_id: str) -> dict[str, Any]:
    """Read the agent's scratchpad for this battle. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    session = _gateway.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    return {"scratchpad": getattr(session, "scratchpad", "")}


@mcp.tool()
async def write_scratchpad(token: str, battle_id: str, text: str) -> dict[str, Any]:
    """Write to the agent's scratchpad for this battle. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    session = _gateway.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    session.scratchpad = text[:1000]
    return {"ok": True, "scratchpad": session.scratchpad}


@mcp.tool()
async def request_evolution(token: str, team: str, reasoning: str) -> dict[str, Any]:
    """Request evolution seeds for a team. Required scope: 'evolve'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="evolve")
        _gateway.authority.spend_quota(claims, scope="evolve")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    if _sidecar_fn is None:
        raise ValueError("Sidecar factory not registered")

    try:
        sidecar = await _sidecar_fn()
        return await offer_seeds(
            sidecar,
            current_team=team or None,
            reasoning=sanitize_name(reasoning, max_len=200),
        )
    except Exception as e:
        raise ValueError(f"Evolution request error: {e}") from None


@mcp.tool()
async def get_my_ladder_history(token: str) -> dict[str, Any]:
    """Get the battle and ladder history for this agent. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    events = []
    if _gateway.events.path.is_file():
        for ev in _gateway.events.iter_events():
            payload = ev.get("payload") or {}
            if payload.get("tenant_id") == claims.token_id:
                events.append(ev)
    return {"events": events}


@mcp.tool()
async def get_battle_replay(battle_id: str) -> dict[str, Any]:
    """Get the public replay data for a battle."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    data = _gateway.replays.get(battle_id)
    if data is None:
        raise ValueError(f"Replay not found: {battle_id}")
    return {
        "input_log": data["input_log"],
        "winner": data["winner"],
        "lane": data["lane"],
        "parent": data.get("parent"),
    }


@mcp.tool()
async def get_evolution_diff(token: str) -> dict[str, Any]:
    """Get the Glicko rating evolution difference for the agent. Required scope: 'battle'."""
    if _gateway is None:
        raise ValueError("Gateway not initialized")
    try:
        claims = _gateway.authority.verify(token, scope="battle")
    except ConsentError as e:
        raise ValueError(f"Unauthorized: {e}") from None

    if not _gateway.events.path.is_file():
        return {
            "agent_name": claims.agent_name,
            "current_rating": 1500.0,
            "rating_diff": 0.0,
            "note": "No games played yet",
        }

    ladder = recompute_ladder(_gateway.events.path)
    r = ladder.entrants.get(claims.agent_name)
    if r is None:
        return {
            "agent_name": claims.agent_name,
            "current_rating": 1500.0,
            "rating_diff": 0.0,
            "note": "No games played yet",
        }

    diff = r.rating - 1500.0
    return {
        "agent_name": claims.agent_name,
        "current_rating": round(r.rating, 1),
        "rating_deviation": round(r.rd, 1),
        "rating_diff": round(diff, 1),
        "games_played": r.games,
    }
