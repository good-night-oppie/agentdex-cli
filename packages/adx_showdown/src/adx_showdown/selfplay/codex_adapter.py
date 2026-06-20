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

from collections.abc import Callable, Mapping
from typing import Any

# Strategies the runner routes to this adapter (the codex move seam).
CODEX_STRATEGIES: frozenset[str] = frozenset({"llm_freeform", "codex"})

# A live-codex hook: (harness, codex_context) -> chosen action id — a move id or a
# switch species (or None to defer to a random legal order). The default policy has
# this shape too.
DecideFn = Callable[[Any, dict[str, Any]], "str | None"]


def _allow_switch(harness: Any) -> bool:
    """Whether the genome's Contract-1 ``ToolPolicy`` permits a VOLUNTARY switch
    (default ``True`` when unset / duck-typed). A FORCED switch is always allowed
    regardless — the player must switch. Reads either the ``BattleHarness`` model OR
    its Contract-1 dict/wire form (``{"tool_policy": {"allow_switch": false}}``), so
    the policy gate holds when the adapter is handed the wire form."""
    tp = (
        harness.get("tool_policy")
        if isinstance(harness, Mapping)
        else getattr(harness, "tool_policy", None)
    )
    if tp is None:
        return True
    val = (
        tp.get("allow_switch", True)
        if isinstance(tp, Mapping)
        else getattr(tp, "allow_switch", True)
    )
    return True if val is None else bool(val)


def _is_forced_switch(battle: Any) -> bool:
    """A MANDATORY switch (KO / forced) — the explicit ``force_switch`` flag, NOT
    merely "no legal move": some no-move turns (every active move disabled) are still
    a VOLUNTARY switch opportunity that ``allow_switch`` must gate."""
    return bool(getattr(battle, "force_switch", False))


def _legal_switches(harness: Any, battle: Any) -> list[Any]:
    """The switch targets the policy may pick this turn: always the forced-switch set,
    but VOLUNTARY switches (``force_switch`` is False) only when the genome's
    ``tool_policy.allow_switch`` is set — so a switch-disabled experiment cannot switch
    as soon as codex names one, even on a non-KO no-move turn (Contract-1 ToolPolicy)."""
    switches = list(getattr(battle, "available_switches", None) or [])
    if not _is_forced_switch(battle) and not _allow_switch(harness):
        return []
    return switches


def codex_context(battle: Any, *, allow_switch: bool = True) -> dict[str, Any]:
    """The JSON-able view of the current turn handed to codex (the harness's
    decision context). Pure: reads only duck-typed battle attributes, no LLM, no
    network — so the same structure feeds a live codex over MCP and the tests.

    ``available_moves`` carries each legal move's id + base_power; ``available_switches``
    carries each legal switch target's species (so the policy can choose a switch —
    on a forced switch after a KO there are NO moves, only switches). ``allow_switch``
    drops VOLUNTARY switches (``force_switch`` is False) so the prompt never offers a
    switch the genome's ToolPolicy forbids. The rest is light situational state."""
    moves = list(getattr(battle, "available_moves", None) or [])
    switches = list(getattr(battle, "available_switches", None) or [])
    if not _is_forced_switch(battle) and not allow_switch:
        switches = []  # voluntary switch disallowed by tool_policy (gated on force_switch)
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
    if decide is None:
        try:
            from agentdex_cli.battle_harness_adapter import select_codex_move as cli_select
        except ImportError:
            cli_select = None

        if cli_select is not None:
            moves = list(getattr(battle, "available_moves", None) or [])
            switches = list(getattr(battle, "available_switches", None) or [])
            choices = []
            for idx, m in enumerate(moves):
                t = getattr(m, "type", None)
                tname = t.name.lower() if t else ""
                choices.append(
                    {
                        "choice_index": len(choices) + 1,
                        "choice": f"move {idx + 1}",
                        "id": str(getattr(m, "id", "") or ""),
                        "name": str(getattr(m, "id", "") or ""),
                        "kind": "move",
                        "base_power": int(getattr(m, "base_power", 0) or 0),
                        "accuracy": float(getattr(m, "accuracy", 100) or 100),
                        "move_type": tname,
                    }
                )
            for s in switches:
                choices.append(
                    {
                        "choice_index": len(choices) + 1,
                        "choice": f"switch {getattr(s, 'species', '')}",
                        "name": str(getattr(s, "species", "") or ""),
                        "kind": "switch",
                    }
                )

            active = getattr(battle, "active_pokemon", None)
            opp_active = getattr(battle, "opponent_active_pokemon", None)
            battle_state = {
                "n_choices": len(choices),
                "choices": choices,
                "own_types": [t.name.lower() for t in active.types if t]
                if active and getattr(active, "types", None)
                else [],
                "opponent_types": [t.name.lower() for t in opp_active.types if t]
                if opp_active and getattr(opp_active, "types", None)
                else [],
                "status": "your_move",
            }

            h_dict = harness
            if not isinstance(h_dict, Mapping) and hasattr(h_dict, "to_dict"):
                h_dict = h_dict.to_dict()
            elif not isinstance(h_dict, Mapping):
                h_dict = {
                    "harness_id": getattr(harness, "harness_id", ""),
                    "move_selection_strategy": getattr(
                        harness, "move_selection_strategy", "max_damage"
                    ),
                    "tool_policy": getattr(harness, "tool_policy", {}),
                    "params": getattr(harness, "params", {}),
                }

            try:
                selection = cli_select(h_dict, battle_state)
                idx = selection.choice_index
                if 1 <= idx <= len(moves):
                    return moves[idx - 1]
                elif len(moves) < idx <= len(moves) + len(switches):
                    return switches[idx - len(moves) - 1]
            except Exception:
                pass

    moves = list(getattr(battle, "available_moves", None) or [])
    allow_switch = _allow_switch(harness)
    switches = _legal_switches(harness, battle)
    if not moves and not switches:
        return None  # nothing legal (forced pass / struggle) → caller's random fallback
    ctx = codex_context(battle, allow_switch=allow_switch)
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
