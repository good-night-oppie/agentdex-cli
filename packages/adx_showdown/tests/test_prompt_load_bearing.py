"""prompt.md is now LOAD-BEARING.

Before: of the five evolution stores only teams.json was behaviorally read; the
Refiner could edit prompt.md/subagents.json/skills.json/memory.json forever and
the falsification rail could not measure any of it (the "measurement illusion"
noted in evolution.py STORE_FILES + locked by test_store_read_tracing).

This wires ONE inert store — prompt.md — onto the behavioral path: the entrant
policy is steered by ``workspace.system_prompt``, so a Refiner edit to prompt.md
now moves the battle outcome. The offline tests prove the steering + that
prompt.md is actually read; the sidecar-gated test is the falsification rail
(two prompt variants must diverge in real play, else prompt.md is still inert).

Closes the load-bearing surface gap from A2A #1271 (eddie-agi-kb review 2026-06-24).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from adx_showdown.bots import hyper_offense_bot, max_damage_bot, stall_bot
from adx_showdown.evolution import (
    HarnessWorkspace,
    _bot_for,
    prompt_steered_policy_factory,
    select_strategy,
    trace_store_reads,
)

_TEAM = "Pikachu||LightBall|Static|Thunderbolt,VoltSwitch||||||"


class _DummySidecar:
    """Construct-only stand-in: archetype bots capture the sidecar in a closure
    but never call it until a turn is played, so policy CONSTRUCTION needs no
    live Node process (the battle-divergence test below uses a real Sidecar)."""


def _ws(tmp: Path, prompt: str) -> HarnessWorkspace:
    return HarnessWorkspace.init(tmp / "ws", team_packed=_TEAM, prompt=prompt)


def test_select_strategy_is_steered_by_the_prompt():
    assert select_strategy("aggressive sweeper — set up and attack") == "offense"
    assert select_strategy("defensive: stall with status + recover") == "stall"
    assert select_strategy("balanced: lay hazards then pivot") == "balance"
    assert select_strategy("win the long game via trick room") == "trickroom"


def test_default_prompt_does_not_change_house_behavior():
    """The init default ("house battler v0") must map to max_damage so existing
    house-lane evolution behavior is unchanged — only a deliberate strategy edit
    moves play (no silent regression)."""
    assert select_strategy("house battler v0") == "max_damage"
    assert select_strategy("") == "max_damage"
    assert _bot_for("max_damage") is max_damage_bot


def test_two_prompts_select_different_archetypes():
    assert _bot_for(select_strategy("aggressive")) is hyper_offense_bot
    assert _bot_for(select_strategy("defensive")) is stall_bot
    assert select_strategy("aggressive") != select_strategy("defensive")


def test_prompt_is_read_on_the_behavioral_path(tmp_path: Path):
    """LOAD-BEARING proof: constructing the entrant policy READS prompt.md, so it
    now registers in trace_store_reads — it was 0 before this wire. If prompt.md
    is ever un-wired, this assertion goes RED."""
    ws = _ws(tmp_path, "aggressive sweeper")
    with trace_store_reads() as reads:
        prompt_steered_policy_factory(ws, _DummySidecar(), 7)  # type: ignore[arg-type]
    assert reads["prompt.md"] >= 1
    # teams.json is NOT read just to build the entrant (team flows in separately)
    assert reads["teams.json"] == 0


# ----------------------------------------------------------------------------- #
# Falsification rail (sidecar-gated, like test_archetype_bots): two prompt.md
# variants must produce DIFFERENT play on the SAME seed + opponent. If prompt.md
# were inert (both runs same policy) every input log would be identical -> RED.
# ----------------------------------------------------------------------------- #

from adx_showdown.bots import max_damage_bot as _md_bot  # noqa: E402
from adx_showdown.sidecar import Sidecar, sidecar_available  # noqa: E402
from adx_showdown.sim import run_battle  # noqa: E402


@pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))
def test_two_prompts_diverge_in_real_play(tmp_path: Path):
    async def _play(prompt: str, seed: int):
        ws = HarnessWorkspace.init(
            tmp_path / f"{select_strategy(prompt)}-{seed}", team_packed=_TEAM, prompt=prompt
        )
        async with Sidecar() as sc:
            return await run_battle(
                sc,
                battle_id=f"diverge-{select_strategy(prompt)}-{seed}",
                format_id="gen9randombattle",
                p1_name="Entrant",
                p2_name="Anchor",
                p1_policy=prompt_steered_policy_factory(ws, sc, seed),
                p2_policy=_md_bot(sc, fallback_seed=seed + 7),
                seed=[seed, 2, 3, 4],
            )

    # CRN-paired across a few seeds; load-bearing if play diverges on ANY seed
    # (an inert prompt.md would make every pair identical).
    diverged = False
    for seed in (101, 202, 303, 404):
        aggro = asyncio.run(_play("aggressive sweeper", seed))
        defen = asyncio.run(_play("defensive stall with status and recover", seed))
        if aggro.input_log != defen.input_log:
            diverged = True
            break
    assert diverged, "two prompt.md variants produced identical play — prompt.md is still inert"
