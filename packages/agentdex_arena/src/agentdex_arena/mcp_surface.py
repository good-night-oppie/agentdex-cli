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
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from agentdex_arena.consent import ConsentError, _normalize_owner
from agentdex_arena.gateway import INTERRUPTED_RESTART_MSG, ArenaGateway
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
) -> Any:
    """Verify bearer consent token, returning claims.

    Converts malformed, expired, revoked, or wrong-scope ConsentErrors into
    a generic opaque error to prevent leak of inner details (P2 PR #50 comment follow-up).

    Auth ONLY — this NEVER spends quota. Quota debits are Class B
    (spend-after-success): a tool runs its fallible work first and debits +
    durably records the slot only on success, mirroring HTTP
    /evolution/request. Spending here (before the work) durably over-counts a
    request that later fails — exhausting the caller's cap after a restart for
    work that produced nothing (PR #284 review 3435334329).
    """
    try:
        return gateway.authority.verify(token, scope=scope)
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
        # After a gateway restart the in-memory session is gone; if THIS owner begun
        # (or forked) it in a prior process, signal the restart clearly instead of an
        # ambiguous "not found" the agent reads as its own bug (PR #246 review).
        if gw._interrupted.get(battle_id) == claims.token_id:
            raise ValueError(INTERRUPTED_RESTART_MSG)
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    await gw._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.forfeiting:
        # A concurrent caller is mid-forfeit (timeout) and session.ended is not set YET —
        # mirror the HTTP /state + /choose terminal-in-progress guard (PR #378): surface a
        # transient, retriable error instead of a stale your_move (PR #381 review
        # 3443812751). The agent retries and gets the ended timeout receipt.
        raise ValueError("battle is finishing (timed out) — retry")

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
        # After a gateway restart the in-memory session is gone; if THIS owner begun
        # (or forked) it in a prior process, signal the restart clearly instead of an
        # ambiguous "not found" the agent reads as its own bug (PR #246 review).
        if gw._interrupted.get(battle_id) == claims.token_id:
            raise ValueError(INTERRUPTED_RESTART_MSG)
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    await gw._expire_if_stale(session)
    if session.ended is not None:
        return {"status": "ended", **session.ended}

    if session.forfeiting:
        # Concurrent in-flight forfeit (timeout) — do NOT step the sidecar (it would race
        # the concurrent stop); surface a transient, retriable error mirroring the HTTP
        # /choose guard (PR #378 / PR #381 review 3443812751). The agent retries and gets
        # the ended timeout receipt.
        raise ValueError("battle is finishing (timed out) — retry")

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
        # After a gateway restart the in-memory session is gone; if THIS owner begun
        # (or forked) it in a prior process, signal the restart clearly instead of an
        # ambiguous "not found" the agent reads as its own bug (PR #246 review).
        if gw._interrupted.get(battle_id) == claims.token_id:
            raise ValueError(INTERRUPTED_RESTART_MSG)
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
        # After a gateway restart the in-memory session is gone; if THIS owner begun
        # (or forked) it in a prior process, signal the restart clearly instead of an
        # ambiguous "not found" the agent reads as its own bug (PR #246 review).
        if gw._interrupted.get(battle_id) == claims.token_id:
            raise ValueError(INTERRUPTED_RESTART_MSG)
        raise ValueError(f"Battle session not found: {battle_id}")

    if claims.token_id != session.claims_token_id:
        raise ValueError("Unauthorized: token does not own this battle")

    session.scratchpad = text[:1000]
    return {"ok": True, "scratchpad": session.scratchpad}


@mcp.tool()
async def request_evolution(token: str, team: str, reasoning: str) -> dict[str, Any]:
    """Request evolution seeds for a team. Required scope: 'evolve'."""
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="evolve")
    # Fast-fail BEFORE the expensive sidecar work if the daily evolve cap is
    # already hit (read-only). The authoritative debit + durable quota_spend
    # record happen only AFTER offer_seeds succeeds, mirroring HTTP
    # /evolution/request — so a failed seed generation can neither burn nor (post
    # ADX-P2-004) durably record a slot (Class B spend-after-success). PR #284
    # review 3435334329.
    try:
        gw.authority.check_quota(claims, scope="evolve")
    except ConsentError as e:
        raise _opaque_mcp_error("evolve quota", e) from None

    sc_fn = _get_sidecar_fn()
    try:
        sidecar = await sc_fn()
        result = await offer_seeds(
            sidecar,
            current_team=team or None,
            reasoning=sanitize_name(reasoning, max_len=200),
        )
    except Exception as e:
        raise ValueError(f"Evolution request error: {e}") from None

    try:
        _, spent_key = gw.authority.spend_quota(claims, scope="evolve")
    except ConsentError as e:
        raise _opaque_mcp_error("evolve quota", e) from None
    # Durable so the daily evolve cap survives a restart (ADX-P2-004).
    gw._record_quota_spend(spent_key)
    return result


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


# --- Self-play meta-harness surface (ADR-0014 / SPEC Lane A4, Contract 2) -------
# The tool codex drives to run one self-play matchup and read the Contract-2
# BattleResult the meta-harness fitness consumes. Eval, not a rated battle.

_MAX_SELFPLAY_BATTLES = 50


def _validate_selfplay_args(
    harness_a: dict[str, Any], harness_b: dict[str, Any], n_battles: int
) -> tuple[Any, Any, int]:
    """Pure: parse the two harness genomes + clamp n_battles to [1, MAX].

    Side-effect-free (no gateway, no PS server) so the input contract codex must
    satisfy is unit-testable on its own. Raises on a malformed genome."""
    from adx_showdown.harness import BattleHarness

    a = BattleHarness.model_validate(harness_a)
    b = BattleHarness.model_validate(harness_b)
    n = max(1, min(int(n_battles), _MAX_SELFPLAY_BATTLES))
    return a, b, n


def _selfplay_opponent_label(harness_b: Any) -> str:
    """A trusted opponent label for the Contract-2 ``raw_dims``, DERIVED from the
    opponent harness — never the MCP caller. The self-play opponent is always a
    candidate harness (never a real held-out baseline Player), so the label is
    namespaced (``harness:<id>``) to guarantee it can never collide with a
    held-out Elo anchor (RandomPlayer / MaxBasePowerPlayer / SimpleHeuristicsPlayer).
    Otherwise a caller could name a weak ``harness_b`` after a strong baseline and
    inflate the ``multi_dim_fitness`` Elo / kill-gate without changing the battle."""
    return f"harness:{harness_b.harness_id}"


@mcp.tool()
async def selfplay_battle(
    token: str,
    harness_a: dict[str, Any],
    harness_b: dict[str, Any],
    seed: int,
    n_battles: int = 10,
    mode: str | None = None,
) -> dict[str, Any]:
    """Run a self-play matchup on the Pokémon Showdown server: ``harness_a`` (the
    candidate) vs ``harness_b`` over ``n_battles``, returning the Contract-2
    BattleResult (winner + raw_dims the meta-harness fitness consumes). This is
    the evolution-loop surface codex drives (ADR-0014); it is EVAL, not a rated
    arena battle, so it spends NO battle quota. Required scope: 'battle'. Needs a
    running PS server (ADX_PS_HOST/PORT); ``n_battles`` is capped at 50.

    Optional ``mode`` (``solo_bots|pvp|team|selfplay``, the GA-SELFPLAY-EVOLVE
    arena-mode contract): when set, the runner resolves the battle format via the
    ``team_modes`` substrate instead of the default ``gen9randombattle``. ``None``
    keeps existing behavior (back-compat for current MCP callers). Modes that
    resolve to a doubles or ``team_required`` format raise
    ``RunnerNotReadyForFormat`` today — fail-loud, not silently broken — until
    the player-side increments (per-slot decision + team-builder) land.

    The opponent label in the result is DERIVED from ``harness_b`` (never caller-
    supplied), so a run cannot be mislabeled as having beaten an anchored held-out
    baseline to inflate the fitness / kill-gate.

    Self-play is free EVAL (no quota debit) BUT a leaked battle token must not be
    able to spawn unbounded concurrent PS battles and starve the shared pool. So
    one in-flight slot per NORMALIZED owner is reserved here — reusing the SAME
    per-owner concurrency admission rated battles use (ADR-0012 §7,
    ``_reserve_owner_slot``), capped at ``ARENA_MAX_BATTLES_PER_OWNER`` — and
    released in a finally. This is an availability rail (finite battle slots), not
    a quota/economics meter and not a PoP/protocol change: a leaked token can still
    run free eval, just not monopolize the server (#483).
    """
    gw = _get_gateway()
    claims = _verify_token_opaque(gw, token, scope="battle")
    # A malformed genome is the driving agent's own (actionable) input, not an
    # anti-enumeration surface — surface a clear message, not an opaque ref.
    try:
        a, b, n = _validate_selfplay_args(harness_a, harness_b, n_battles)
    except Exception as e:
        raise ValueError(f"invalid self-play harness genome: {e}") from None

    # Reserve synchronously BEFORE the first await (so concurrent calls from one
    # owner can't burst past the cap); a 429 is the caller's actionable signal.
    owner_norm = _normalize_owner(claims.owner)
    try:
        gw._reserve_owner_slot(owner_norm)
    except HTTPException as e:
        raise ValueError(str(e.detail)) from None

    from adx_showdown.selfplay import run_selfplay_battle

    try:
        result = await run_selfplay_battle(
            a,
            b,
            seed=int(seed),
            n_battles=n,
            opponent_baseline=_selfplay_opponent_label(b),
            mode=mode,
        )
    except Exception as e:  # PS-server / poke-env failure
        raise _opaque_mcp_error("selfplay_battle", e) from None
    finally:
        gw._release_owner_slot(owner_norm)
    return result.model_dump()
