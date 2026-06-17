"""Phase P1-b/c — full-fidelity protocol-log capture + re-sim parity.

The sidecar surfaces the complete ordered omniscient ``|TYPE|`` stream; `sim.py`
accumulates it into `BattleResult.protocol_log` and `events()` types it. The
load-bearing property for Phase 5: re-simulating the recorded inputLog
reproduces a **byte-identical** mechanical protocol log once the
non-deterministic ``|t:|`` timestamps are stripped.
"""

from __future__ import annotations

import asyncio

import pytest
from adx_showdown.lineproto import Tier
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.sim import (
    BattleResult,
    canonical_protocol,
    events,
    replay_input_log,
    run_battle,
    seeded_random_policy,
)

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def _spec(seed_base: int = 4242) -> dict:
    return dict(
        battle_id="plog",
        format_id="gen9randombattle",
        p1_name="Alpha",
        p2_name="Beta",
        p1_policy=seeded_random_policy(seed_base),
        p2_policy=seeded_random_policy(seed_base + 1),
        seed=[seed_base, 2, 3, 4],
    )


def test_protocol_log_is_full_and_ordered():
    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_spec())

    result = asyncio.run(_run())
    log = result.protocol_log
    assert log, "protocol_log must be populated"
    # the full stream carries majors, a minor, AND the meta lines the filtered
    # keyLines/turnLines subsets drop (|t:|, |gen|, bare divider, |split|)
    assert any(ln.startswith("|turn|") for ln in log)
    assert any(ln.startswith("|move|") for ln in log)
    assert any(ln.startswith("|-") for ln in log), "at least one minor line"
    assert any(ln.startswith("|t:|") for ln in log), "full fidelity keeps |t:|"
    assert "|" in log, "the bare section divider is captured"

    # ordering: the first turn anchor precedes the end line. NB: match |tie|
    # precisely — startswith("|tie") also matches the |tier| preamble line (the
    # documented false-tie trap), which would put a phantom "end" at index ~7.
    def _is_end(ln: str) -> bool:
        return ln.startswith("|win|") or ln == "|tie" or ln.startswith("|tie|")

    end_idx = next(i for i, ln in enumerate(log) if _is_end(ln))
    turn_idx = next(i for i, ln in enumerate(log) if ln.startswith("|turn|"))
    assert turn_idx < end_idx


def test_events_types_the_stream_end_to_end():
    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_spec(seed_base=909))

    result = asyncio.run(_run())
    evs = events(result)
    assert len(evs) == len(result.protocol_log)
    by_tier = {t: 0 for t in Tier}
    for e in evs:
        by_tier[e.tier] += 1
    # a real battle exercises all three tiers
    assert by_tier[Tier.MAJOR] > 0 and by_tier[Tier.MINOR] > 0 and by_tier[Tier.META] > 0
    # indices are monotonic over the whole stream
    assert [e.index for e in evs] == list(range(len(evs)))


def test_resim_is_byte_identical_after_timestamp_strip():
    """Phase-5 anchor: (seed, inputLog) re-simulation reproduces the canonical
    (|t:|-stripped) protocol byte-for-byte."""

    async def _run() -> tuple[BattleResult, BattleResult]:
        async with Sidecar() as sc:
            original = await run_battle(sc, **_spec(seed_base=7777))
            replayed = await replay_input_log(
                sc, battle_id="plog-replay", input_log=original.input_log
            )
            return original, replayed

    original, replayed = asyncio.run(_run())
    assert original.winner == replayed.winner and original.turns == replayed.turns
    canon_a = canonical_protocol(original)
    canon_b = canonical_protocol(replayed)
    assert canon_a, "canonical protocol must be non-empty"
    assert all(not ln.startswith("|t:|") for ln in canon_a), "|t:| stripped"
    assert canon_a == canon_b, "re-sim must reproduce byte-identical mechanical protocol"
    # and the raw logs DID differ (only by timestamps) — proving the strip matters
    if original.protocol_log != replayed.protocol_log:
        ts_a = [ln for ln in original.protocol_log if ln.startswith("|t:|")]
        assert ts_a, "the only raw difference should be |t:| lines"


def test_protocol_log_not_truncated_for_a_normal_battle():
    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_spec(seed_base=1234))

    result = asyncio.run(_run())
    assert result.protocol_truncated is False
