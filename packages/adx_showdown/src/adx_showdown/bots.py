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


# Archetype move categories (FUN-3 / design note 2026-06-12)
SETUP_MOVES = {
    "swordsdance",
    "dragondance",
    "calmmind",
    "nastyplot",
    "quiverdance",
    "bulkup",
    "shellsmash",
    "agility",
    "irondefense",
    "acidarmor",
    "cosmicpower",
    "doubleteam",
    "minimize",
    "amnesia",
    "barrier",
    "growth",
    "workup",
    "honeclaws",
    "coil",
    "curse",
    "autoclave",
}

HAZARD_MOVES = {"stealthrock", "spikes", "toxicspikes", "stickyweb"}
PIVOT_MOVES = {"uturn", "voltswitch", "chillyreception", "flipturn", "partingshot"}
STATUS_MOVES = {"thunderwave", "willowisp", "toxic", "yawn", "glare", "spore", "stunspore"}
RECOVERY_MOVES = {
    "recover",
    "roost",
    "slackoff",
    "softboiled",
    "moonlight",
    "rest",
    "synthesis",
    "wish",
}
PROTECT_MOVES = {"protect", "spikyshield", "banefulbunker", "kingsshield"}
TRICK_ROOM_MOVES = {"trickroom"}


def _active_hp_pct(req: ParsedRequest) -> float:
    active = next((p for p in req.bench if p.active), None)
    if not active or not active.condition:
        return 100.0
    cond = active.condition.split()[0]
    if cond == "0" or active.condition.endswith("fnt"):
        return 0.0
    if "/" in cond:
        try:
            curr, max_hp = cond.split("/", 1)
            return (float(curr) / float(max_hp)) * 100.0
        except ValueError:
            return 100.0
    return 100.0


async def _stab_max_damage(
    sidecar: Sidecar,
    req: ParsedRequest,
    ctx: BattleContext,
    candidates: list[tuple[int, str]],
) -> str:
    if not ctx.opponent_species:
        return f"move {candidates[0][0]}"
    resp = await sidecar.request(
        "dex-rate",
        moves=[mid for _, mid in candidates],
        defender=ctx.opponent_species,
        attacker=ctx.my_species,
    )
    ratings: dict[str, float] = {k: float(v) for k, v in resp["ratings"].items()}
    best_slot, _ = max(candidates, key=lambda sm: (ratings.get(sm[1], 0.0), -sm[0]))
    return f"move {best_slot}"


def _archetype_base(sidecar: Sidecar, *, fallback_seed: int = 0):
    """Shared preamble for archetype gym bots."""
    fallback = seeded_random_policy(fallback_seed)

    async def _preamble(req: ParsedRequest) -> tuple[str | None, list[tuple[int, str]] | None]:
        if req.wait:
            return None, None
        if req.team_preview:
            return "team 1", None
        if req.force_switch and any(req.force_switch):
            return _first_switch(req), None
        candidates = _enabled_move_ids(req)
        if not candidates:
            return fallback(req), None
        return None, candidates

    return fallback, _preamble


def balance_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Archetype: balance — hazards, pivots, selective setup, then damage."""
    _fallback, preamble = _archetype_base(sidecar, fallback_seed=fallback_seed)
    hazards_laid = 0

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        nonlocal hazards_laid
        early, candidates = await preamble(req)
        if early is not None:
            return early
        if candidates is None:
            return None

        hp_pct = _active_hp_pct(req)

        hazard_candidates = [(s, m) for s, m in candidates if m in HAZARD_MOVES]
        if hazard_candidates and hazards_laid < 1:
            hazards_laid += 1
            return f"move {hazard_candidates[0][0]}"

        pivot_candidates = [(s, m) for s, m in candidates if m in PIVOT_MOVES]
        has_bench = any(not slot.active and not slot.fainted for slot in req.bench)
        if pivot_candidates and has_bench and hp_pct >= 40.0:
            return f"move {pivot_candidates[0][0]}"

        return await _stab_max_damage(sidecar, req, ctx, candidates)

    return _policy


def hyper_offense_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Archetype: hyper-offense — setup aggressively, then STAB-weighted sweep."""
    _fallback, preamble = _archetype_base(sidecar, fallback_seed=fallback_seed)

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        early, candidates = await preamble(req)
        if early is not None:
            return early
        if candidates is None:
            return None

        return await _stab_max_damage(sidecar, req, ctx, candidates)

    return _policy


def stall_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Archetype: stall — hazards, status, recovery, protect, then damage."""
    _fallback, preamble = _archetype_base(sidecar, fallback_seed=fallback_seed)
    hazards_laid = 0
    statused_opponents: set[str] = set()

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        nonlocal hazards_laid
        early, candidates = await preamble(req)
        if early is not None:
            return early
        if candidates is None:
            return None

        hp_pct = _active_hp_pct(req)

        hazard_candidates = [(s, m) for s, m in candidates if m in HAZARD_MOVES]
        if hazard_candidates and hazards_laid < 3:
            hazards_laid += 1
            return f"move {hazard_candidates[0][0]}"

        status_candidates = [(s, m) for s, m in candidates if m in STATUS_MOVES]
        if (
            status_candidates
            and ctx.opponent_species
            and ctx.opponent_species not in statused_opponents
        ):
            statused_opponents.add(ctx.opponent_species)
            return f"move {status_candidates[0][0]}"

        recovery_candidates = [(s, m) for s, m in candidates if m in RECOVERY_MOVES]
        if recovery_candidates and hp_pct < 60.0:
            return f"move {recovery_candidates[0][0]}"

        return await _stab_max_damage(sidecar, req, ctx, candidates)

    return _policy


def trick_room_bot(sidecar: Sidecar, *, fallback_seed: int = 0) -> Policy:
    """Archetype: trick-room — set Trick Room once, then slow-pressure damage."""
    _fallback, preamble = _archetype_base(sidecar, fallback_seed=fallback_seed)
    trick_room_used = False

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        nonlocal trick_room_used
        early, candidates = await preamble(req)
        if early is not None:
            return early
        if candidates is None:
            return None

        tr_candidates = [(s, m) for s, m in candidates if m in TRICK_ROOM_MOVES]
        if tr_candidates and not trick_room_used:
            trick_room_used = True
            return f"move {tr_candidates[0][0]}"

        return await _stab_max_damage(sidecar, req, ctx, candidates)

    return _policy
