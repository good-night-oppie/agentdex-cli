"""Synchronous-step battle driver + inputLog re-simulation (A2 grounding).

Determinism contract (go/no-go 2026-06-11, hardened same day): battles advance
via the sidecar's STEP protocol — submit choices for every pending side in one
`step`, receive the next pending requests in the response. Showdown commits
turns synchronously inside `stream.write`, the sidecar drains before replying,
and choices are written in fixed p1-then-p2 order, so the outcome is a pure
function of (battle seed, policy decisions). Event-driven lockstep was
measured to diverge run-to-run (choice arrival races on request re-emission);
this protocol has no events to race.
"""

from __future__ import annotations

import asyncio
import inspect
import random
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.protocol import (
    ParsedRequest,
    fainted_switch_choices,
    legal_choices,
    move_only_choices,
    parse_request,
    sanitize_name,
    switch_only_choices,
)
from adx_showdown.sidecar import Sidecar

Policy = Callable[..., "str | None | Awaitable[str | None]"]
"""Maps a parsed request to a choice string (None = no action, e.g. wait).

Two call shapes, sniffed once per battle: ``policy(req)`` or
``policy(req, ctx)`` where ctx is a :class:`BattleContext`. Either may be
async (bots that consult the sidecar's dex-rate op are).
"""


class BattleContext(BaseModel):
    """Per-step context handed to 2-arg policies (bots need the defender)."""

    model_config = ConfigDict(extra="forbid", strict=False)
    side: str
    my_species: str | None = None
    opponent_species: str | None = None
    turns: int = 0


def _wants_context(policy: Policy) -> bool:
    try:
        params = [
            pm
            for pm in inspect.signature(policy).parameters.values()
            if pm.kind in (pm.POSITIONAL_ONLY, pm.POSITIONAL_OR_KEYWORD)
        ]
        return len(params) >= 2
    except (TypeError, ValueError):
        return False


async def _call_policy(
    policy: Policy, req: ParsedRequest, ctx: BattleContext, *, wants_ctx: bool
) -> str | None:
    result = policy(req, ctx) if wants_ctx else policy(req)
    if inspect.isawaitable(result):
        result = await result
    return result


def first_legal_policy(req: ParsedRequest) -> str | None:
    choices = legal_choices(req)
    return choices[0] if choices else None


def seeded_random_policy(seed: int) -> Policy:
    rng = random.Random(seed)

    def _policy(req: ParsedRequest) -> str | None:
        choices = legal_choices(req)
        return rng.choice(choices) if choices else None

    return _policy


class BattleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    battle_id: str
    winner: str  # SANITIZED player name; "" == tie
    turns: int
    input_log: list[str] = Field(default_factory=list)
    key_lines: list[str] = Field(default_factory=list)  # signature extraction input
    choice_errors: int = 0
    steps: int = 0


class BattleFailed(RuntimeError):
    """Battle ended with a sidecar/stream error rather than a result."""


def _fallback_choice(req: ParsedRequest | None, error: str) -> str | None:
    """Deterministic recovery when Showdown rejects a choice.

    `maybeTrapped` is only revealed on rejection ("Can't switch: ... trapped"),
    so the driver MUST re-choose or the battle deadlocks (measured: stall at
    the first Arena Trap / Shadow Tag encounter). First-of-set keeps the run
    deterministic — no extra RNG draws on the error path.
    """
    if req is None:
        return None
    low = error.lower()
    if "fainted" in low:
        pool = fainted_switch_choices(req) or ["pass"]
    elif "switch" in low:
        pool = move_only_choices(req)
    elif "move" in low:
        pool = switch_only_choices(req)
    else:
        pool = legal_choices(req)
    return pool[0] if pool else None


def _result_from_end(
    battle_id: str, end: dict[str, Any], *, choice_errors: int, steps: int
) -> BattleResult:
    if end.get("streamError"):
        raise BattleFailed(f"{battle_id}: stream error: {end['streamError']}")
    return BattleResult(
        battle_id=battle_id,
        winner=sanitize_name(end.get("winner") or ""),
        turns=int(end.get("turns", 0)),
        input_log=list(end.get("inputLog") or []),
        key_lines=list(end.get("keyLines") or []),
        choice_errors=choice_errors,
        steps=steps,
    )


async def run_battle(
    sidecar: Sidecar,
    *,
    battle_id: str,
    format_id: str,
    p1_name: str,
    p2_name: str,
    p1_policy: Policy,
    p2_policy: Policy,
    seed: list[int] | None = None,
    p1_team: str | None = None,
    p2_team: str | None = None,
    max_choice_errors: int = 25,
    max_steps: int = 5000,
) -> BattleResult:
    """Run one battle to completion via the step protocol; sanitized result."""
    policies: dict[str, Policy] = {"p1": p1_policy, "p2": p2_policy}
    # Teams in random formats are drawn from PER-PLAYER seeds (battle.js
    # getTeam), distinct from the battle PRNG seed. Derive them from the
    # battle seed so one `seed` argument pins the whole battle.
    p1_seed = [seed[0] + 1, seed[1], seed[2], seed[3]] if seed and p1_team is None else None
    p2_seed = [seed[0] + 2, seed[1], seed[2], seed[3]] if seed and p2_team is None else None
    resp = await sidecar.request(
        "start",
        battle=battle_id,
        format=format_id,
        seed=seed,
        p1={"name": p1_name, "team": p1_team, "seed": p1_seed},
        p2={"name": p2_name, "team": p2_team, "seed": p2_seed},
    )
    state: dict[str, Any] = resp["state"]
    choice_errors = 0
    last_req: dict[str, ParsedRequest] = {}
    wants_ctx = {side: _wants_context(policies[side]) for side in ("p1", "p2")}
    OTHER = {"p1": "p2", "p2": "p1"}

    for step_n in range(1, max_steps + 1):
        if state.get("end"):
            return _result_from_end(
                battle_id, state["end"], choice_errors=choice_errors, steps=step_n - 1
            )
        choices: dict[str, str] = {}
        # error corrections take precedence over fresh policy calls
        for err in state.get("errors", []):
            side = err.get("side", "")
            choice_errors += 1
            if choice_errors > max_choice_errors:
                raise BattleFailed(
                    f"{battle_id}: exceeded {max_choice_errors} choice errors; "
                    f"last: {err.get('error', '')[:200]}"
                )
            retry = _fallback_choice(last_req.get(side), err.get("error", ""))
            if side and retry is not None:
                choices[side] = retry
        for side in ("p1", "p2"):
            if side in choices:
                continue
            raw = (state.get("pending") or {}).get(side)
            if raw is None:
                continue
            req = parse_request(raw)
            last_req[side] = req
            ctx = BattleContext(
                side=side,
                my_species=(state.get("active") or {}).get(side),
                opponent_species=(state.get("active") or {}).get(OTHER[side]),
                turns=int(state.get("turns", 0)),
            )
            choice = await _call_policy(policies[side], req, ctx, wants_ctx=wants_ctx[side])
            if choice is not None:
                choices[side] = choice
        if not choices:
            raise BattleFailed(
                f"{battle_id}: no pending choices and battle not ended "
                f"(turns={state.get('turns')}) — protocol stall"
            )
        resp = await sidecar.request("step", battle=battle_id, choices=choices)
        state = resp["state"]

    raise BattleFailed(f"{battle_id}: exceeded {max_steps} steps")


async def replay_input_log(
    sidecar: Sidecar,
    *,
    battle_id: str,
    input_log: list[str],
) -> BattleResult:
    """Re-simulate a recorded input log verbatim (A2: outsider-verifiable)."""
    resp = await sidecar.request("replay", battle=battle_id, lines=list(input_log))
    end = (resp.get("state") or {}).get("end")
    if not end:
        raise BattleFailed(
            f"{battle_id}: replay did not reach an end state "
            f"(turns={(resp.get('state') or {}).get('turns')})"
        )
    return _result_from_end(battle_id, end, choice_errors=0, steps=0)


async def run_concurrent_battles(
    sidecar: Sidecar,
    specs: list[dict[str, Any]],
) -> list[BattleResult]:
    """Run several battles concurrently on ONE sidecar process.

    The sidecar serializes op handling globally (FIFO chain), so concurrent
    drivers interleave at step granularity without corrupting battles.
    """
    return list(await asyncio.gather(*(run_battle(sidecar, **spec) for spec in specs)))
