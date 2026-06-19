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

import math
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    # allow_inf_nan=False: a non-finite float knob (nan/inf) is not a valid JSON
    # scalar and breaks the advertised round-trip once it crosses a persistence /
    # API boundary — and bene WILL mutate params freely, so reject it at the door.
    model_config = ConfigDict(extra="forbid", strict=False, allow_inf_nan=False)

    harness_id: str = Field(min_length=1)
    system_prompt: str = ""
    move_selection_strategy: str = Field(default="max_damage", min_length=1)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    params: dict[str, ParamValue] = Field(default_factory=dict)

    @field_validator("params")
    @classmethod
    def _params_are_json_finite(cls, v: dict[str, ParamValue]) -> dict[str, ParamValue]:
        """Reject non-finite float knobs (belt-and-suspenders over allow_inf_nan).

        `bool` is a subclass of `int`; only genuine floats can be nan/inf, so the
        check is `isinstance(x, float)` — and that also catches a float-typed
        bene mutation regardless of how the `ParamValue` union coerced it."""
        for key, val in v.items():
            if isinstance(val, float) and not math.isfinite(val):
                raise ValueError(f"param {key!r} is non-finite ({val!r}); not a valid JSON scalar")
        return v


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


# --------------------------------------------------------------------------- #
# Cross-repo Contract-1 seam.
#
# Two genome implementations exist by design: THIS validated pydantic model is
# the **canonical Contract-1 type** — it owns the schema + the validation that IS
# the contract (non-empty id, finite params, ``extra="forbid"``). bene's
# ``bene.kernel.battle.genome.BattleHarness`` is a plain dataclass bene mutates.
# The two stay decoupled (neither repo imports the other), so the JSON dict is the
# wire between them. These named adapters ARE that seam: every crossing goes
# through the canonical model, so a bene-side field drift surfaces as a
# ``ValidationError`` at the boundary instead of a mystery failure inside a
# battle (SPEC Contract 1 / ADR-0014 "reconcile then").
# --------------------------------------------------------------------------- #


def from_bene_genome(data: BattleHarness | Mapping[str, Any]) -> BattleHarness:
    """Adapt a bene Contract-1 genome dict (``bene.kernel.battle.genome.
    BattleHarness.to_dict()``) into the canonical, validated genome. Accepts an
    already-canonical ``BattleHarness`` unchanged. Raises ``pydantic.Validation
    Error`` if bene's shape ever drifts from the contract."""
    if isinstance(data, BattleHarness):
        return data
    return BattleHarness.model_validate(dict(data))


def to_bene_genome(harness: BattleHarness) -> dict[str, Any]:
    """Adapt the canonical genome back into the plain JSON dict shape bene's
    ``BattleHarness.from_dict`` consumes (``tool_policy`` flattened to a dict)."""
    return harness.model_dump()
