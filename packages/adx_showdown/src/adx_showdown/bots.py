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
    """Anchor 3 — max-damage upgraded twice (measured: the v1
    switch-when-resisted rule LOST to max-damage 0.42, bleeding momentum):

    1. STAB-weighted move rating (dex-rate `attacker` param, ×1.5) — strictly
       better damage ordering than raw basePower×effectiveness.
    2. Bench-aware forced switches: rate every healthy bench mon's best move
       against the current defender and switch to the best matchup, instead
       of first-legal.
    """
    fallback = seeded_random_policy(fallback_seed)

    async def _best_bench_switch(req: ParsedRequest, defender: str) -> str | None:
        best: tuple[float, int] | None = None
        for slot in req.bench:
            if slot.active or slot.fainted or not slot.moves:
                continue
            resp = await sidecar.request(
                "dex-rate", moves=slot.moves, defender=defender, attacker=slot.species
            )
            power = max((float(v) for v in resp["ratings"].values()), default=0.0)
            if best is None or power > best[0]:
                best = (power, slot.index)
        return f"switch {best[1]}" if best else _first_switch(req)

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        if req.wait:
            return None
        if req.team_preview:
            return "team 1"
        if req.force_switch and any(req.force_switch):
            if ctx.opponent_species:
                return await _best_bench_switch(req, ctx.opponent_species)
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
            attacker=ctx.my_species,
        )
        ratings: dict[str, float] = {k: float(v) for k, v in resp["ratings"].items()}
        best_slot, _best_id = max(candidates, key=lambda sm: (ratings.get(sm[1], 0.0), -sm[0]))
        return f"move {best_slot}"

    return _policy
