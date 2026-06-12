"""Scripted anchor bots (ADR-0010 phase 4 — zero-LLM-cost opponents).

Three anchors, intended ordering random < max-damage < heuristic. They power
calibration (phase 5: anchor ordering with non-overlapping 2·RD is the
instrument self-test) and serve as gym leaders / sparring partners, all at
$0 LLM cost (IDEAL §Arena A7).
"""

from __future__ import annotations

from adx_showdown.protocol import ParsedRequest, legal_choices
from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import BattleContext, Policy, seeded_random_policy


def random_bot(seed: int) -> Policy:
    """Anchor 1 — uniform over legal choices (seeded)."""
    return seeded_random_policy(seed)


def _enabled_move_ids(req: ParsedRequest) -> list[tuple[int, str]]:
    """[(slot, move_id)] for enabled moves of the first active slot."""
    out: list[tuple[int, str]] = []
    for moves in req.active_moves[:1]:
        for mv in moves:
            if not mv.disabled and mv.id:
                out.append((mv.slot, mv.id))
    return out


def _first_switch(req: ParsedRequest) -> str | None:
    for c in legal_choices(req):
        if c.startswith("switch"):
            return c
    return None


def max_damage_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Anchor 2 — highest effective power (basePower × type-effectiveness)
    against the current opposing species, via the sidecar's dex-rate op.
    Deterministic: ties break on lowest slot; no RNG draws on the move path.
    """
    fallback = seeded_random_policy(fallback_seed)

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        if req.wait:
            return None
        if req.team_preview:
            return "team 1"
        if req.force_switch and any(req.force_switch):
            return _first_switch(req)
        candidates = _enabled_move_ids(req)
        if not candidates:
            return fallback(req)
        if not ctx.opponent_species:
            return f"move {candidates[0][0]}"
        resp = await sidecar.request(
            "dex-rate",
            moves=[mid for _, mid in candidates],
            defender=ctx.opponent_species,
        )
        ratings: dict[str, float] = {k: float(v) for k, v in resp["ratings"].items()}
        best_slot, _ = max(candidates, key=lambda sm: (ratings.get(sm[1], 0.0), -sm[0]))
        return f"move {best_slot}"

    return _policy


def heuristic_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Anchor 3 — max-damage plus two heuristics: switch out when every move
    is resisted-or-worse (max effective power < 40), and never click a move
    the defender is immune to when an effective switch exists.
    """
    fallback = seeded_random_policy(fallback_seed)
    SWITCH_THRESHOLD = 40.0

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        if req.wait:
            return None
        if req.team_preview:
            return "team 1"
        if req.force_switch and any(req.force_switch):
            return _first_switch(req)
        candidates = _enabled_move_ids(req)
        if not candidates:
            return fallback(req)
        if not ctx.opponent_species:
            return f"move {candidates[0][0]}"
        resp = await sidecar.request(
            "dex-rate",
            moves=[mid for _, mid in candidates],
            defender=ctx.opponent_species,
        )
        ratings: dict[str, float] = {k: float(v) for k, v in resp["ratings"].items()}
        best_slot, best_id = max(
            candidates, key=lambda sm: (ratings.get(sm[1], 0.0), -sm[0])
        )
        if ratings.get(best_id, 0.0) < SWITCH_THRESHOLD and not req.trapped:
            switch = _first_switch(req)
            if switch is not None:
                return switch
        return f"move {best_slot}"

    return _policy
