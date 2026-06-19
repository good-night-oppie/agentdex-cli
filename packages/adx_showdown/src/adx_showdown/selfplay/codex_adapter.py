"""C1 — codex's battle move adapter (SPEC Lane C, Contract 5; ADR-0014).

This is the seam where **codex drives Showdown self-play moves through the
agentdex-cli arena MCP surface** (SPEC DONE criterion #1). The arena's
``selfplay_battle`` MCP tool (A4) runs a matchup whose candidate moves are
resolved by ``adx_showdown.selfplay.runner``; when a harness's
``move_selection_strategy`` is a codex strategy (``llm_freeform`` / ``codex``),
the runner routes each turn's decision here.

Per Contract 5 the harness's ``system_prompt`` + ``params`` **are** codex's
policy — the thing under evolution — so a live codex/LLM plugs into the
``decide`` hook, reading the harness + a JSON-able ``codex_context`` view of the
turn and returning a move id. With no hook (the default, and what runs in tests
and the offline demonstration) a deterministic **greedy** policy chooses the
highest-base-power legal move. The contract is identical either way: the adapter
returns one of ``battle.available_moves`` (or ``None`` → the caller falls back to
a random legal order), so swapping the live LLM in changes only the *decision*,
never the wiring.

Kept pure (no poke-env import, no network) so it is unit-testable on a duck-typed
battle and adds nothing to the non-codex move path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Strategies the runner routes to this adapter (the codex move seam).
CODEX_STRATEGIES: frozenset[str] = frozenset({"llm_freeform", "codex"})

# A live-codex hook: (harness, codex_context) -> chosen move id (or None to defer
# to a random legal order). The default policy below has this shape too.
DecideFn = Callable[[Any, dict[str, Any]], "str | None"]


def codex_context(battle: Any) -> dict[str, Any]:
    """The JSON-able view of the current turn handed to codex (the harness's
    decision context). Pure: reads only duck-typed battle attributes, no LLM, no
    network — so the same structure feeds a live codex over MCP and the tests.

    ``available_moves`` carries each legal move's id + base_power (the minimum a
    greedy or an LLM policy needs); the rest is light situational state."""
    moves = list(getattr(battle, "available_moves", None) or [])
    active = getattr(battle, "active_pokemon", None)
    return {
        "available_moves": [
            {
                "id": str(getattr(m, "id", "") or ""),
                "base_power": int(getattr(m, "base_power", 0) or 0),
            }
            for m in moves
        ],
        "active_species": str(getattr(active, "species", "") or "") if active else "",
        "active_hp_fraction": float(getattr(active, "current_hp_fraction", 0.0) or 0.0)
        if active
        else 0.0,
        "force_switch": bool(getattr(battle, "force_switch", False)),
    }


def _greedy_decide(harness: Any, ctx: dict[str, Any]) -> str | None:
    """The default codex policy when no live LLM is wired: pick the highest-
    base-power available move. A live codex/LLM replaces this via ``decide``,
    reading ``harness.system_prompt`` + ``harness.params`` to play freeform."""
    avail = ctx.get("available_moves") or []
    if not avail:
        return None
    return max(avail, key=lambda m: m.get("base_power", 0))["id"]


def select_codex_move(harness: Any, battle: Any, *, decide: DecideFn | None = None) -> Any | None:
    """Return the poke-env move codex chooses this turn (for ``create_order``),
    or ``None`` when there is no legal move (the caller falls back to a random
    legal order).

    ``decide(harness, codex_context) -> move_id`` is the live-codex hook; the
    default is the deterministic greedy policy. A decided id that is not among
    the legal moves falls back to the first available move (defensive — a live
    LLM cannot force an illegal move through this seam)."""
    moves = list(getattr(battle, "available_moves", None) or [])
    if not moves:
        return None
    ctx = codex_context(battle)
    chooser = decide or _greedy_decide
    move_id = chooser(harness, ctx)
    if move_id is None:
        return None
    for m in moves:
        if str(getattr(m, "id", "") or "") == str(move_id):
            return m
    return moves[0]


__all__ = ["select_codex_move", "codex_context", "CODEX_STRATEGIES", "DecideFn"]
