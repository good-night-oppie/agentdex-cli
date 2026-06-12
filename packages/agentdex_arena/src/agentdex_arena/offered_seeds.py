"""Offered seeds — visitor evolution is OFFERED, never applied (A5/F2).

We do not control visiting agents' harnesses; the only component the gateway
provably applies is the TEAM. So: team-mutation seeds are server-validated
(the measured lane), everything else ships as advisory data permanently
labeled `application_unverified: true` and excluded from all delta claims.
"""

from __future__ import annotations

from typing import Any

from adx_showdown.sidecar import Sidecar
from adx_showdown.teams import pack_team, starter_pack, validate_team

ADVISORY_SEEDS = [
    {
        "kind": "prompt",
        "description": "Render the type chart for both actives before choosing; "
        "immune/resisted clicks dominate the failure signatures we see.",
        "application_unverified": True,
    },
    {
        "kind": "memory",
        "description": "Track which of the opponent's mons have been revealed; "
        "switch decisions improve sharply with a seen-team ledger.",
        "application_unverified": True,
    },
    {
        "kind": "skill",
        "description": "Before a rated battle, replay your last sandbox loss from "
        "its /replay inputLog and identify the first divergent turn.",
        "application_unverified": True,
    },
]


async def offer_seeds(
    sidecar: Sidecar,
    *,
    current_team: str | None,
    reasoning: str,
) -> dict[str, Any]:
    """Return measured team-mutation candidates + advisory seeds.

    Team candidates are drawn from the curated starter pack, server-packed
    and validate-team-gated — a visitor can only ever apply a VALID team
    (mutation-not-composition, F3)."""
    pack = starter_pack()
    candidates = []
    for name, export_text in list(pack.items())[:3]:
        packed = await pack_team(sidecar, export_text)
        if current_team is not None and packed == current_team:
            continue
        valid, errors = await validate_team(sidecar, packed)
        if valid:
            candidates.append(
                {
                    "kind": "team_mutation",
                    "name": name,
                    "packed": packed,
                    "measured_lane": True,  # gateway-applied => delta-claimable
                }
            )
    return {
        "reasoning_echo": reasoning,  # sanitized upstream
        "team_candidates": candidates,
        "advisory_seeds": ADVISORY_SEEDS,
        "note": "advisory seeds are application-unverified and excluded from delta claims (A5)",
    }
