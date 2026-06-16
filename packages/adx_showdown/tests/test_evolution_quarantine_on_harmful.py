"""Regression lock for the P0 'HARMFUL rollback leaves the ladder lying' bug.

`_rate` appends a window's RatingEvents to the period log BEFORE the verdict is
known. On HARMFUL, `rollback_to_best_ever()` restores the git-backed STORES but
never touches events.jsonl — so without a quarantine the reverted team's losses
stay baked into `recompute_ladder`, and the published rating + the A4 receipt
advertise a team that was rolled back. The fix emits one `quarantine` event per
battle_id in the rolled-back window; `recompute_ladder` pre-scans for them and
filters those battles out of every period.

Stand-alone + sidecar-free: `_quarantine_window` only touches the event log, so
this exercises the real ladder-impact reversion without the pokemon-showdown
sidecar (the full HARMFUL run is covered by the sidecar-gated
test_injected_nerf_detected_harmful_and_rolled_back in test_evolution.py).
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.evolution import EvolutionLoop, HarnessWorkspace
from adx_showdown.sim import BattleResult
from agentdex_engine.modules.arena.events import EventLog, recompute_ladder

_ENTRANT = "house-evolver"
_ANCHOR = "anchor-opponent"


def _loop(tmp_path: Path) -> EvolutionLoop:
    ws = HarnessWorkspace.init(
        tmp_path / "ws", team_packed="Pikachu||Light Ball|Static|Thunderbolt||||||"
    )
    return EvolutionLoop(
        workspace=ws,
        opponent_factory=lambda *_a: None,  # unused by _rate/_quarantine_window
        events_path=tmp_path / "events.jsonl",
        entrant=_ENTRANT,
        anchor=_ANCHOR,
    )


def _all_losses(gen: int, k: int) -> list[BattleResult]:
    """A window the entrant LOST outright — the shape a HARMFUL nerf produces."""
    return [BattleResult(battle_id=f"live-g{gen}-b{i}", winner=_ANCHOR, turns=1) for i in range(k)]


def test_quarantine_reverts_the_rolled_back_window_on_the_ladder(tmp_path: Path):
    loop = _loop(tmp_path)
    loop._register()
    baseline = recompute_ladder(loop.events_path).rating(_ENTRANT).rating

    results = _all_losses(gen=1, k=5)
    loop._rate(results, gen=1)
    after_losses = recompute_ladder(loop.events_path).rating(_ENTRANT).rating
    # The harmful window dropped the published rating.
    assert after_losses < baseline

    loop._quarantine_window(results)
    after_quarantine = recompute_ladder(loop.events_path).rating(_ENTRANT).rating
    # Quarantine reverts the ladder impact — back to the pre-window baseline.
    assert after_quarantine == baseline
    assert after_quarantine > after_losses


def test_quarantine_emits_one_event_per_battle(tmp_path: Path):
    loop = _loop(tmp_path)
    loop._register()
    results = _all_losses(gen=2, k=3)
    loop._rate(results, gen=2)
    loop._quarantine_window(results)

    elog = EventLog(loop.events_path)
    quarantined = {
        e["payload"]["battle_id"] for e in elog.iter_events() if e["type"] == "quarantine"
    }
    assert quarantined == {"live-g2-b0", "live-g2-b1", "live-g2-b2"}


def test_period_event_is_preserved_not_rewritten(tmp_path: Path):
    """Anti-history-rewrite: the period stays in the log (truthfully recording
    the battles happened); only a quarantine is appended to void them. Append-
    only audit integrity — no event is ever deleted."""
    loop = _loop(tmp_path)
    loop._register()
    results = _all_losses(gen=1, k=2)
    loop._rate(results, gen=1)
    loop._quarantine_window(results)

    elog = EventLog(loop.events_path)
    types = [e["type"] for e in elog.iter_events()]
    assert types.count("period") == 1  # the period was NOT removed
    assert types.count("quarantine") == 2  # voided additively
