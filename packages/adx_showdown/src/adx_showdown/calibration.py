"""Anchor calibration — the instrument's self-test (ADR-0010 phase 5).

Runs seeded machine-speed battles between the three scripted anchors, rates
them on a fresh Ladder via the hash-chained event log, and asserts the known
ordering random < max_damage < heuristic with non-overlapping 2·RD intervals.
Publication halts when this fails (the nightly job exits non-zero and the
gateway refuses to publish — EVAL §Arena row 4).

Battle allocation is biased toward the CLOSE pair (max_damage vs heuristic,
measured 0.68 win rate ≈ 130 Elo) because random-vs-anything separates in a
handful of battles (measured 1.00 ≈ off-scale).

Calibration rates in a SINGLE period (period_size=200): one full-information
Glicko-2 update from RD=350 separates the close pair in 200 battles
(measured: gap 235 > 2·(39.6+39.6)), where 10 incremental periods left the
gap at 47 (slow convergence as shrinking RD damps later updates). The
production ladder still uses generation-sized periods; single-period is a
calibration-only choice — its job is detecting anchor ORDER inversions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agentdex_engine.modules.arena import EventLog, Ladder, recompute_ladder

from adx_showdown.bots import heuristic_bot, max_damage_bot, random_bot
from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import run_battle

ANCHORS = ("anchor-random", "anchor-max_damage", "anchor-heuristic")


def _policy_for(name: str, sidecar: Sidecar, seed: int):
    kind = name.removeprefix("anchor-")
    if kind == "random":
        return random_bot(seed)
    if kind == "max_damage":
        return max_damage_bot(sidecar, fallback_seed=seed)
    return heuristic_bot(sidecar, fallback_seed=seed)


async def run_calibration(
    events_path: str | Path,
    *,
    total_battles: int = 200,
    close_pair_share: float = 0.7,
    seed_base: int = 20_000,
    period_size: int = 200,
) -> dict[str, Any]:
    """Run the calibration tournament; returns the report dict.

    Report keys: ratings (name -> {rating, rd, games}), ordering_ok,
    separation_ok, battles, periods. The committed calibration report and
    the nightly self-test both render from this.
    """
    close = int(total_battles * close_pair_share)
    far = total_battles - close
    pairs = (
        [("anchor-max_damage", "anchor-heuristic")] * close
        + [("anchor-random", "anchor-max_damage")] * (far // 2)
        + [("anchor-random", "anchor-heuristic")] * (far - far // 2)
    )

    elog = EventLog(events_path)
    for name in ANCHORS:
        elog.append("register", {"name": name, "frozen": False})

    period: list[dict[str, Any]] = []
    periods = 0
    async with Sidecar() as sidecar:
        for i, (a, b) in enumerate(pairs):
            seed = [seed_base + i, 7, 8, 9]
            result = await run_battle(
                sidecar,
                battle_id=f"calib-{i}",
                format_id="gen9randombattle",
                p1_name=a,
                p2_name=b,
                p1_policy=_policy_for(a, sidecar, seed_base + i * 2),
                p2_policy=_policy_for(b, sidecar, seed_base + i * 2 + 1),
                seed=seed,
            )
            period.append(
                {
                    "battle_id": result.battle_id,
                    "p1": a,
                    "p2": b,
                    "winner": result.winner,
                    "input_log_blake2b16": hashlib.blake2b(
                        "\n".join(result.input_log).encode(), digest_size=16
                    ).hexdigest(),
                }
            )
            if len(period) >= period_size:
                elog.append("period", {"events": period})
                period = []
                periods += 1
    if period:
        elog.append("period", {"events": period})
        periods += 1

    ladder = recompute_ladder(events_path)
    r = {name: ladder.rating(name) for name in ANCHORS}
    ordering_ok = (
        r["anchor-random"].rating < r["anchor-max_damage"].rating < r["anchor-heuristic"].rating
    )
    separation_ok = not Ladder.intervals_overlap(
        r["anchor-random"], r["anchor-max_damage"]
    ) and not Ladder.intervals_overlap(r["anchor-max_damage"], r["anchor-heuristic"])
    return {
        "battles": len(pairs),
        "periods": periods,
        "ratings": {
            name: {"rating": rt.rating, "rd": rt.rd, "games": rt.games}
            for name, rt in r.items()
        },
        "ordering_ok": ordering_ok,
        "separation_ok": separation_ok,
        "publication_allowed": ordering_ok and separation_ok,
    }
