"""BattleHarness genome — the unit bene mutates in the self-play meta-harness loop.

This is **Contract 1** of the self-play meta-harness work-order
(`tasks/selfplay-metaharness/SPEC.md`, ADR-0014): a JSON-serializable description
of *how an agent plays a battle*. Lane A defines it; bene (Lane B) perturbs
`system_prompt` + `params` + `move_selection_strategy`; codex (Lane C) receives a
harness + battle state over MCP and the harness's prompt/params ARE its policy.

Kept deliberately small and pure (no sim imports) so every lane can depend on it
without pulling the battle engine. `run_selfplay_battle` (A1) resolves
`move_selection_strategy` to an `adx_showdown.sim.Policy`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Strategies A1's resolver can turn into a concrete sim Policy. `move_selection_
# strategy` is NOT hard-restricted to this set — bene may explore novel names and
# A1 falls back deterministically — but these are the known-resolvable values.
# The bot-backed names mirror adx_showdown.bots; `llm_freeform` defers the choice
# to codex (Lane C) over MCP.
KNOWN_STRATEGIES: frozenset[str] = frozenset(
    {
        "random",
        "max_damage",
        "heuristic",
        "balance",
        "hyper_offense",
        "stall",
        "trick_room",
        "llm_freeform",
    }
)

# JSON scalar knobs bene is allowed to perturb in `params`.
ParamValue = float | int | str | bool


class ToolPolicy(BaseModel):
    """What battle tools the harness may use (Contract 1 `tool_policy`)."""

    model_config = ConfigDict(extra="forbid", strict=False)

    allow_switch: bool = True
    lookahead_depth: int = Field(default=1, ge=0)


class BattleHarness(BaseModel):
    """A battle-playing harness genome (Contract 1).

    JSON round-trips via :meth:`pydantic.BaseModel.model_dump` /
    ``model_validate`` so bene can mutate the dict form and hand it back. bene
    mutates ``system_prompt``, ``params``, and ``move_selection_strategy``;
    ``harness_id`` identifies a genome in the lineage.
    """

    model_config = ConfigDict(extra="forbid", strict=False)

    harness_id: str = Field(min_length=1)
    system_prompt: str = ""
    move_selection_strategy: str = Field(default="max_damage", min_length=1)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    params: dict[str, ParamValue] = Field(default_factory=dict)


def seed_harness() -> BattleHarness:
    """The seed harness H0 — the baseline bene's first generation mutates from.

    A reasonable, non-degenerate starting policy: pick high-damage moves, switch
    out of bad matchups, never forfeit. The evolved harness must beat THIS on
    held-out baselines (the kill gate) for the run to count.
    """
    return BattleHarness(
        harness_id="H0-seed",
        system_prompt=(
            "You are a competitive Pokémon battler. Each turn pick the move or "
            "switch that maximizes win probability: favor high-damage and "
            "super-effective moves, switch away from a losing matchup, never pick "
            "an illegal move, and never forfeit."
        ),
        move_selection_strategy="max_damage",
        tool_policy=ToolPolicy(allow_switch=True, lookahead_depth=1),
        params={"aggression": 1.0, "switch_threshold_hp": 0.25, "risk_tolerance": 0.5},
    )
