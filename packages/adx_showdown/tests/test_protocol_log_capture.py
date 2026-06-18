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


def test_run_battle_sanitizes_player_names_into_the_log():
    """An unsanitized caller name must be stripped at the source so the |player|
    meta line + |win| winner in the protocol log carry no untrusted metachars.
    PR #201 review 3431865007."""

    async def _run() -> BattleResult:
        spec = _spec(seed_base=8675)
        spec["p1_name"] = "Evil|/forfeit<script>"
        async with Sidecar() as sc:
            return await run_battle(sc, **spec)

    result = asyncio.run(_run())
    player_lines = [ln for ln in result.protocol_log if ln.startswith("|player|p1|")]
    assert player_lines, "the |player| meta line must be captured"
    for ch in ("|/", "<", ">"):
        assert ch not in player_lines[0], f"unsanitized {ch!r} reached the |player| line"
    # the sanitized name is what survives (the allowlist keeps letters)
    assert "Evilforfeitscript" in player_lines[0]


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


def test_protocol_log_includes_request_control_lines():
    """sideupdate |request| (and |error|) control lines are captured into the
    protocol log so events(result) is the single reducer input that can also
    reconstruct the decision pane. PR #201 review 3431865001."""
    import json

    from adx_showdown.sim import events

    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_spec(seed_base=555))

    result = asyncio.run(_run())
    req_lines = [ln for ln in result.protocol_log if ln.startswith("|request|")]
    assert req_lines, "|request| control lines must be in the protocol log"
    # the side is recoverable from the request JSON (it stayed intact — opaque type)
    payload = json.loads(req_lines[0][len("|request|") :])
    assert payload.get("side", {}).get("id") in ("p1", "p2")
    # events() types them as opaque request events with a single intact JSON arg
    reqs = [e for e in events(result) if e.type == "request"]
    assert reqs and len(reqs[0].args) == 1


def test_protocol_log_not_truncated_for_a_normal_battle():
    async def _run() -> BattleResult:
        async with Sidecar() as sc:
            return await run_battle(sc, **_spec(seed_base=1234))

    result = asyncio.run(_run())
    assert result.protocol_truncated is False


def test_cumulative_truncation_is_consistent_across_resim(monkeypatch):
    """With a tiny cap, the CUMULATIVE line count truncates both the live battle
    and its replay at the same point, so the canonical protocols still match.
    A per-step (buffer-length) cap would let the live battle keep its whole log
    while replay truncated — breaking re-sim parity. PR #201 review 3431864995.
    """
    monkeypatch.setenv("ADX_SIDECAR_MAX_PROTOCOL_LINES", "25")

    async def _run() -> tuple[BattleResult, BattleResult]:
        async with Sidecar() as sc:
            original = await run_battle(sc, **_spec(seed_base=31337))
            replayed = await replay_input_log(
                sc, battle_id="trunc-replay", input_log=original.input_log
            )
            return original, replayed

    original, replayed = asyncio.run(_run())
    # a full gen9 battle is >25 lines, so BOTH paths truncate at the cumulative cap
    assert original.protocol_truncated is True
    assert replayed.protocol_truncated is True
    assert len(original.protocol_log) <= 25
    # truncation is consistent → canonical (|t:|-stripped) protocols still agree
    assert canonical_protocol(original) == canonical_protocol(replayed)


def test_byte_cap_truncates_consistently_across_resim(monkeypatch):
    """A long battle can stay UNDER the line cap yet exceed the 16 MiB Python
    readline budget because each captured |request| carries the side's roster JSON.
    The companion BYTE cap bounds the log on the SERIALIZED size (so |request| JSON
    escaping is counted, not just raw bytes — PR #221 review); with a tiny budget
    both the live battle and its replay truncate at the same cumulative point, so
    re-sim parity holds (a per-step byte cap would diverge). PR #214 review 3432149322."""
    import json

    monkeypatch.setenv("ADX_SIDECAR_MAX_PROTOCOL_BYTES", "512")  # well under one battle

    async def _run() -> tuple[BattleResult, BattleResult]:
        async with Sidecar() as sc:
            original = await run_battle(sc, **_spec(seed_base=42424))
            replayed = await replay_input_log(
                sc, battle_id="bytecap-replay", input_log=original.input_log
            )
            return original, replayed

    original, replayed = asyncio.run(_run())
    assert original.protocol_truncated is True  # byte budget hit before the line cap
    assert replayed.protocol_truncated is True
    # the stored log is a contiguous prefix bounded by the SERIALIZED byte budget —
    # mirror the sidecar's JSON.stringify accounting (ensure_ascii=False ≈ JS)
    serialized = sum(
        len(json.dumps(ln, ensure_ascii=False).encode("utf-8")) + 1 for ln in original.protocol_log
    )
    assert serialized <= 512
    # consistent truncation point → canonical (|t:|-stripped) protocols still agree
    assert canonical_protocol(original) == canonical_protocol(replayed)
