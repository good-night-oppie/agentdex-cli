"""Phase-A5 — anchor calibration + signature extraction on real battles.

The full 200-battle calibration runs nightly (cron/arena_selftest.sh) and its
committed report lives at docs/references/2026-06-12-arena-calibration.md.
CI runs a reduced-budget version asserting the same rails: known ordering,
publication gate wiring, event-chain integrity, recompute determinism.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from adx_showdown.calibration import run_calibration
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.sim import run_battle, seeded_random_policy
from agentdex_engine.modules.arena import EventLog, extract_signatures, recompute_ladder

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


@pytest.mark.timeout(600)
def test_calibration_ordering_and_gate(tmp_path: Path):
    """Reduced-budget calibration: ordering must hold; gate must be wired to
    BOTH rails (a passing run flips publication_allowed only when ordering
    AND separation hold)."""
    events = tmp_path / "events.jsonl"
    report = asyncio.run(run_calibration(events, total_battles=60, seed_base=40_000))
    print(f"\nCALIBRATION_60: {report['ratings']}")
    assert report["ordering_ok"], report
    assert report["publication_allowed"] == (report["ordering_ok"] and report["separation_ok"])
    # A8: the calibration's own event log verifies + recomputes identically
    assert EventLog(events).verify_chain() >= 2
    l1, l2 = recompute_ladder(events), recompute_ladder(events)
    assert l1.entrants == l2.entrants


def test_signatures_extracted_from_real_battle():
    async def _run():
        async with Sidecar() as sc:
            return await run_battle(
                sc,
                battle_id="sig-probe",
                format_id="gen9randombattle",
                p1_name="SigA",
                p2_name="SigB",
                p1_policy=seeded_random_policy(1),
                p2_policy=seeded_random_policy(2),
                seed=[12_345, 1, 2, 3],
            )

    result = asyncio.run(_run())
    assert result.key_lines, "sidecar must surface signature key lines"
    sigs_p1 = extract_signatures(result.key_lines, side="p1")
    assert any(s.signature == "mon_fainted" for s in sigs_p1)
    assert extract_signatures(result.key_lines, side="p1") == sigs_p1
    print(f"\nSIGNATURES: {[(s.signature, s.count) for s in sigs_p1]}")
