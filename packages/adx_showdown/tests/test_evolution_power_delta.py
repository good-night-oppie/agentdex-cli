"""Regression lock for the P0 falsy-zero delta bug in the house EvolutionLoop.

`EvolutionLoop.run_generation` fed the POWERED/INCONCLUSIVE power check via
`abs(delta) if delta else 50.0`. When the ladder genuinely measured a delta of
`0.0` (two teams truly equal), `0.0` is falsy, so the code substituted a
fabricated 50-Elo move and reported a made-up POWERED verdict for a window that
measured exactly NO difference. The fix routes through `_power_input_delta`,
which only falls back to the sentinel when the measurement is *missing*
(`glicko_delta is None`), never for a real `0.0`.

Stand-alone (not in test_evolution.py) because that module is gated by
`skipif(sidecar_available() is not None)` — these assertions are on pure
functions and must run in CI even without the pokemon-showdown sidecar.
"""

from __future__ import annotations

from adx_showdown.evolution import _MISSING_DELTA_SENTINEL, _power_input_delta
from agentdex_engine.modules.arena.power import window_verdict


def test_real_zero_delta_passes_through_as_zero_not_sentinel():
    """A measured 0.0 must stay 0.0 — the bug turned it into the 50.0 sentinel."""
    assert _power_input_delta(0.0) == 0.0
    assert _power_input_delta(0.0) != _MISSING_DELTA_SENTINEL


def test_missing_delta_uses_sentinel():
    """None (the <2*RD no-measurement case) still falls back to the sentinel."""
    assert _power_input_delta(None) == _MISSING_DELTA_SENTINEL


def test_negative_delta_uses_absolute_value():
    """A negative measured delta feeds its magnitude to the power check."""
    assert _power_input_delta(-3.5) == 3.5
    assert _power_input_delta(-0.0) == 0.0


def test_zero_delta_verdict_differs_from_sentinel_verdict():
    """Materiality: a real 0.0 delta yields INCONCLUSIVE (no finite window can
    'power' a detection of zero difference), whereas the fabricated 50.0
    sentinel can read POWERED for a large window. The pre-fix code reported the
    POWERED verdict for a genuinely-zero result; this asserts the two paths
    truly diverge so the bug was material, not cosmetic."""
    big_window = 1_000_000
    # The 50-Elo sentinel is detectable with enough battles -> POWERED.
    assert window_verdict(_MISSING_DELTA_SENTINEL, battles=big_window) == "POWERED"
    # A genuine 0.0 delta is never detectable by a finite window -> INCONCLUSIVE.
    assert window_verdict(_power_input_delta(0.0), battles=big_window) == "INCONCLUSIVE"
