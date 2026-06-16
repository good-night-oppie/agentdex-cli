"""MCP surface — streamable-HTTP MCP server (A8).

Exposes tools for visiting agents to interact with the Pokémon Showdown arena
without requiring permanent WebSockets or SSE connections, keeping it lightweight
and sleeping-tolerant.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any, Literal

from adx_showdown.protocol import legal_choices, sanitize_name
from agentdex_engine.modules.arena import recompute_ladder
from mcp.server.fastmcp import FastMCP

from agentdex_arena.consent import ConsentError
from agentdex_arena.gateway import ArenaGateway
from agentdex_arena.offered_seeds import offer_seeds

logger = logging.getLogger(__name__)

mcp = FastMCP("agentdex-arena")
mcp.settings.streamable_http_path = "/"
mcp.settings.json_response = True
mcp.settings.stateless_http = True
if mcp.settings.transport_security is not None:
    mcp.settings.transport_security.enable_dns_rebinding_protection = False

# Global references set at runtime (as a fallback)
_gateway: ArenaGateway | None = None
_sidecar_fn: Any = None

# Context variables for isolated multi-app support (P2 PR #50 comment follow-up)
current_gateway: contextvars.ContextVar[ArenaGateway | None] = contextvars.ContextVar(
    "current_gateway", default=None
)
current_sidecar_fn: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "current_sidecar_fn", default=None
)


def _get_gateway() -> ArenaGateway:
    gw = current_gateway.get()
    if gw is not None:
        return gw
    if _gateway is not None:
        return _gateway
    raise ValueError("Gateway not initialized")


def _get_sidecar_fn() -> Any:
    sc = current_sidecar_fn.get()
    if sc is not None:
        return sc
    if _sidecar_fn is not None:
        return _sidecar_fn
    raise ValueError("Sidecar function not initialized")


def _verify_token_opaque(
    gateway: ArenaGateway,
    token: str,
    scope: Literal["enroll", "battle", "evolve"],
    spend_quota_scope: Literal["enroll", "battle", "evolve"] | None = None,
) -> Any:
    """Verify bearer consent token, returning claims.

    Converts malformed, expired, revoked, or wrong-scope ConsentErrors into
    a generic opaque error to prevent leak of inner details (P2 PR #50 comment follow-up).
    """
    try:
        claims = gateway.authority.verify(token, scope=scope)
        if spend_quota_scope:
            gateway.authority.spend_quota(claims, scope=spend_quota_scope)
        return claims
    except ConsentError as e:
        err_id = uuid.uuid4().hex[:12]
        logger.warning("mcp auth error (ref=%s): %s", err_id, e)
        raise ValueError(f"arena error (ref: {err_id})") from None


def _opaque_mcp_error(label: str, exc: Exception | str) -> ValueError:
    """Mirror gateway._opaque_error for the MCP path (PR #169 review #3423698025).

    MCP tool errors surface to the visiting agent verbatim, so any
    ``raise ValueError(f"... {e!r}")`` leaks local exception detail —
    filesystem paths, errno strings, sidecar internals. Mirror what HTTP
    does on equivalent failure modes: log the detail server-side with a
    correlation ref, then raise ValueError with just the ref. Use for any
    NEW visitor-facing failure mode introduced after the original
    enroll/auth boundary (which already uses ``_verify_token_opaque``).
    """
    err_id = uuid.uuid4().hex[:12]
    logger.warning("mcp arena error (label=%s, ref=%s): %s", label, err_id, exc)
    return ValueError(f"arena error (ref: {err_id})")


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
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    session = gw.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    await gw._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.pending is None:
        raise ValueError("No pending request in session")

    if session.last_state is None:
        raise ValueError("No state available to render")

    return gw._render(session, session.last_state)


@mcp.tool()
async def choose_action(token: str, battle_id: str, choice_index: int) -> dict[str, Any]:
    """Choose an action in a battle session by index. Required scope: 'battle'."""
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    session = gw.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    await gw._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.pending is None:
        raise ValueError("No pending request in session")

    choices = legal_choices(session.pending)
    if not 1 <= choice_index <= len(choices):
        raise ValueError(f"Choice index out of range 1..{len(choices)}")

    choice = choices[choice_index - 1]

    from agentdex_arena.gateway import _choice_label, _push_recent

    label = _choice_label(choice, session.pending)
    old_recent = list(session.recent)
    old_pending = session.pending
    # Order MUST mirror the HTTP /choose path (gateway.py): step the sidecar
    # FIRST, and only append the audit "battle" row AFTER the move actually
    # executed. The earlier MCP order appended the EventLog row before the step,
    # so a sidecar failure left a chain row recording a move that never ran (the
    # finally below can roll back session state but NOT a durable chain row) —
    # codex dogfood P1 (PASS 27/28).
    session.visitor_choices.append(choice)
    _push_recent(session, f"T{session.turns}: you → {label}")
    session.pending = None

    sc_fn = _get_sidecar_fn()
    sidecar = None
    success = False
    try:
        sidecar = await sc_fn()
        resp = await sidecar.request(
            "step", battle=battle_id, choices={session.visitor_side: choice}
        )
        success = True
    except Exception as e:
        # Step failed BEFORE the move executed — roll back session state in
        # the finally and surface opaquely; the original `f"Battle step
        # error: {e}"` leaked exception detail (PR #169 review #3423698025).
        raise _opaque_mcp_error("choose:step", e) from None
    finally:
        if not success:
            if len(session.visitor_choices) > 0:
                session.visitor_choices.pop()
            session.recent = old_recent
            session.pending = old_pending

    # The move executed: NOW record it to the audit chain. A write failure here
    # fails CLOSED — end the battle and stop the sidecar — rather than leave a
    # live battle whose moves are not durably logged (mirrors HTTP /choose).
    try:
        gw.events.append(
            "battle",
            {
                "tenant_id": session.claims_token_id,
                "battle_id": battle_id,
                "turn": session.turns,
                "choice": choice,
                "choice_label": label,
                "foe_hp_pct": session.foe_hp_pct if session.foe_species else None,
            },
        )
    except Exception as e:
        session.ended = {
            "winner": "",
            "turns": session.turns,
            "reason": "fatal: event log write failed",
        }
        if sidecar is not None:
            try:
                await sidecar.request("stop", battle=battle_id)
            except Exception:
                pass
        # Opaque visitor-facing error (PR #169 review #3423698025); detail logged.
        raise _opaque_mcp_error("choose:audit-append", e) from None
    session.last_touch = gw.now()
    try:
        return await gw._advance(session, resp["state"], visitor_choice=None)
    except Exception as e:
        # PR #169 review #3423698020: when _advance fails after the initial
        # step succeeded (opponent-policy error / sidecar error during
        # opponent auto-advance), the audit row is already durable but
        # session.pending was cleared and never re-populated. Without
        # fail-closed cleanup the battle is wedged: get_battle_state /
        # choose_action will only report "No pending request" until turn-
        # budget timeout. Mirror the audit-append fail-closed posture: end
        # the battle, stop the sidecar, and surface opaquely.
        session.ended = {
            "winner": "",
            "turns": session.turns,
            "reason": "fatal: battle advance failed after move executed",
        }
        if sidecar is not None:
            try:
                await sidecar.request("stop", battle=battle_id)
            except Exception:
                pass
        raise _opaque_mcp_error("choose:advance", e) from None


@mcp.tool()
async def read_scratchpad(token: str, battle_id: str) -> dict[str, Any]:
    """Read the agent's scratchpad for this battle. Required scope: 'battle'."""
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    session = gw.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    return {"scratchpad": getattr(session, "scratchpad", "")}


@mcp.tool()
async def write_scratchpad(token: str, battle_id: str, text: str) -> dict[str, Any]:
    """Write to the agent's scratchpad for this battle. Required scope: 'battle'."""
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    session = gw.sessions.get(battle_id)
    if session is None:
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    session.scratchpad = text[:1000]
    return {"ok": True, "scratchpad": session.scratchpad}


@mcp.tool()
async def request_evolution(token: str, team: str, reasoning: str) -> dict[str, Any]:
    """Request evolution seeds for a team. Required scope: 'evolve'."""
    gw = _get_gateway()
    _verify_token_opaque(gw, token, scope="evolve", spend_quota_scope="evolve")

    sc_fn = _get_sidecar_fn()
    try:
        sidecar = await sc_fn()
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
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    events = []
    if gw.events.path.is_file():
        for ev in gw.events.iter_events():
            payload = ev.get("payload") or {}
            if payload.get("tenant_id") == claims.token_id:
                events.append(ev)
    return {"events": events}


@mcp.tool()
async def get_battle_replay(battle_id: str) -> dict[str, Any]:
    """Get the public replay data for a battle."""
    gw = _get_gateway()
    data = gw.replays.get(battle_id)
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
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")

    if not gw.events.path.is_file():
        return {
            "agent_name": claims.agent_name,
            "current_rating": 1500.0,
            "rating_diff": 0.0,
            "note": "No games played yet",
        }

    ladder = recompute_ladder(gw.events.path)
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
