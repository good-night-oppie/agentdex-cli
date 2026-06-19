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
turn and returning an action id (a move id OR a switch species). With no hook (the
default, and what runs in tests and the offline demonstration) a deterministic
**greedy** policy chooses the highest-base-power legal move, or the first legal
switch on a forced switch. The contract is identical either way: the adapter
returns one of ``battle.available_moves`` / ``battle.available_switches`` (or
``None`` → the caller falls back to a random legal order), so swapping the live LLM
in changes only the *decision*, never the wiring.

Kept pure (no poke-env import, no network) so it is unit-testable on a duck-typed
battle and adds nothing to the non-codex move path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Strategies the runner routes to this adapter (the codex move seam).
CODEX_STRATEGIES: frozenset[str] = frozenset({"llm_freeform", "codex"})

# A live-codex hook: (harness, codex_context) -> chosen action id — a move id or a
# switch species (or None to defer to a random legal order). The default policy has
# this shape too.
DecideFn = Callable[[Any, dict[str, Any]], "str | None"]


def codex_context(battle: Any) -> dict[str, Any]:
    """The JSON-able view of the current turn handed to codex (the harness's
    decision context). Pure: reads only duck-typed battle attributes, no LLM, no
    network — so the same structure feeds a live codex over MCP and the tests.

    ``available_moves`` carries each legal move's id + base_power; ``available_switches``
    carries each legal switch target's species (so the policy can choose a switch —
    on a forced switch after a KO there are NO moves, only switches). The rest is
    light situational state."""
    moves = list(getattr(battle, "available_moves", None) or [])
    switches = list(getattr(battle, "available_switches", None) or [])
    active = getattr(battle, "active_pokemon", None)
    return {
        "available_moves": [
            {
                "id": str(getattr(m, "id", "") or ""),
                "base_power": int(getattr(m, "base_power", 0) or 0),
            }
            for m in moves
        ],
        "available_switches": [{"species": str(getattr(s, "species", "") or "")} for s in switches],
        "active_species": str(getattr(active, "species", "") or "") if active else "",
        "active_hp_fraction": float(getattr(active, "current_hp_fraction", 0.0) or 0.0)
        if active
        else 0.0,
        "force_switch": bool(getattr(battle, "force_switch", False)),
    }


def _greedy_decide(harness: Any, ctx: dict[str, Any]) -> str | None:
    """The default codex policy when no live LLM is wired: pick the highest-
    base-power available move, or — on a forced switch (no moves, only switches) —
    the first legal switch. A live codex/LLM replaces this via ``decide``, reading
    ``harness.system_prompt`` + ``harness.params`` to play freeform."""
    moves = ctx.get("available_moves") or []
    if moves:
        return str(max(moves, key=lambda m: m.get("base_power", 0))["id"])
    switches = ctx.get("available_switches") or []
    if switches:
        return str(switches[0].get("species") or "") or None
    return None


def select_codex_move(
    harness: Any,
    battle: Any,
    *,
    decide: DecideFn | None = None,
    on_illegal: Callable[[], None] | None = None,
) -> Any | None:
    """Return the poke-env order codex chooses this turn (a move OR a switch, both
    for ``create_order``), or ``None`` when there is no legal action (the caller
    falls back to a random legal order).

    The action space is BOTH ``available_moves`` (by move id) and
    ``available_switches`` (by species) — so a switch-aware harness policy can pick
    a switch, and a forced switch (after a KO: no moves, only switches) is chosen by
    the policy rather than the runner's random fallback. ``decide(harness,
    codex_context) -> id`` returns a move id or a switch species; the default is the
    deterministic greedy policy. An id matching neither a legal move nor a legal
    switch is an ILLEGAL decision: ``on_illegal`` is invoked (so the runner records
    it in ``raw_dims["illegal_moves"]`` — otherwise a live policy could hallucinate
    an illegal id every turn while ``move_legibility`` stayed a perfect 1.0) before
    falling back to the first legal action (defensive — a live LLM still cannot force
    an illegal order through this seam). An abstaining hook (``decide`` returns
    ``None``) is NOT counted illegal."""
    moves = list(getattr(battle, "available_moves", None) or [])
    switches = list(getattr(battle, "available_switches", None) or [])
    if not moves and not switches:
        return None  # nothing legal (forced pass / struggle) → caller's random fallback
    ctx = codex_context(battle)
    chooser = decide or _greedy_decide
    chosen_id = chooser(harness, ctx)
    if chosen_id is None:
        return None
    chosen_id = str(chosen_id)
    for m in moves:
        if str(getattr(m, "id", "") or "") == chosen_id:
            return m
    for s in switches:
        if str(getattr(s, "species", "") or "") == chosen_id:
            return s
    if on_illegal is not None:
        on_illegal()
    return moves[0] if moves else switches[0]


__all__ = ["select_codex_move", "codex_context", "CODEX_STRATEGIES", "DecideFn"]
