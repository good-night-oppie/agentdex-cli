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
from agentdex_engine.modules.arena.ladder import Ladder

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
    """A window the entrant LOST outright — the shape a HARMFUL nerf produces.

    The battle_ids are deterministic in (gen, i): a retried generation reuses
    the SAME ids, which is exactly what makes the duplicate-id quarantine trap
    in test_retry_duplicate_ids_voided_window_publishes_no_delta possible."""
    return [BattleResult(battle_id=f"live-g{gen}-b{i}", winner=_ANCHOR, turns=1) for i in range(k)]


def _all_wins(gen: int, k: int) -> list[BattleResult]:
    """A window the entrant WON — used to establish a stable rating with small
    rd (distinct `est-` ids so it survives the live-window quarantine)."""
    return [BattleResult(battle_id=f"est-g{gen}-b{i}", winner=_ENTRANT, turns=1) for i in range(k)]


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


def test_post_quarantine_report_values_match_published_ladder(tmp_path: Path):
    """After a HARMFUL quarantine, the values `_harmful_refresh` returns into the
    GenerationReport (rating/rd from the post-quarantine ladder, delta voided)
    must match the published ladder — NOT the stale pre-quarantine `_rate`
    output, which still reflects the voided losing window. Otherwise the A4
    receipt rendered from the report diverges from the ladder — the exact bug
    P0-3 removes, just moved into the report fields (PR #158 review
    #3421911866)."""
    loop = _loop(tmp_path)
    loop._register()
    pre_window = recompute_ladder(loop.events_path).rating(_ENTRANT)

    results = _all_losses(gen=1, k=5)
    stale_rating, _stale_rd, _stale_delta = loop._rate(results, gen=1)
    # `_rate`'s output reflects the (about-to-be-voided) losing window.
    assert stale_rating < pre_window.rating

    loop._quarantine_window(results)
    refreshed_rating, refreshed_rd, refreshed_delta = loop._harmful_refresh()
    post = recompute_ladder(loop.events_path).rating(_ENTRANT)
    # The refreshed report values == the published ladder == the pre-window
    # baseline (a fully-quarantined window reverts exactly), and != the stale
    # `_rate` output the report would otherwise have carried.
    assert (refreshed_rating, refreshed_rd) == (post.rating, post.rd)
    assert refreshed_rating == pre_window.rating
    assert refreshed_rating != stale_rating
    # A voided window sells no move: the delta is unconditionally None.
    assert refreshed_delta is None


def test_retry_duplicate_ids_voided_window_publishes_no_delta(tmp_path: Path):
    """The P2 trap (PR #159 review #3422007501): a generation that fails after
    `_rate` appended the live period but before the verdict is retried, and the
    retry reuses the deterministic `live-g{gen}-b{i}` ids. `_rate` appends a
    SECOND period with the SAME ids, so the quarantine voids them across BOTH
    periods — `post` reverts PAST the retry's pre-window baseline, back to the
    established rating before the abandoned attempt.

    Computing `published_delta(pre_window, post)` then measures the cleanup of
    the duplicate ids, not a real move, and advertises a spurious POSITIVE delta
    on a rolled-back HARMFUL report. `_harmful_refresh` must void it instead."""
    loop = _loop(tmp_path)
    loop._register()
    # Establish a stable rating with a small rd (so 2*rd is small enough that
    # the spurious gap below clears the published_delta threshold — i.e. the
    # trap is reachable, not masked by a fresh entrant's rd=350).
    for g in range(1, 6):
        loop._rate(_all_wins(gen=g, k=8), gen=g)
    established = recompute_ladder(loop.events_path).rating(_ENTRANT)

    # Abandoned attempt: the live period is appended, the entrant loses, then a
    # failure before the verdict abandons the generation (period left on disk).
    live = _all_losses(gen=6, k=8)
    loop._rate(live, gen=6)
    pre_window = recompute_ladder(loop.events_path).rating(_ENTRANT)
    assert pre_window.rating < established.rating  # abandoned losses are live

    # Retry reuses the SAME deterministic ids, appending a second period.
    loop._rate(live, gen=6)

    # HARMFUL verdict on the retry: quarantine voids live-g6-* across BOTH the
    # abandoned and the retry periods (recompute_ladder filters ids globally).
    loop._quarantine_window(live)
    post = recompute_ladder(loop.events_path).rating(_ENTRANT)

    # `post` reverts PAST pre_window all the way to the established rating.
    assert post.rating == established.rating
    assert post.rating != pre_window.rating

    # The trap is real: the old `published_delta(pre_window, post)` would publish
    # a spurious positive move on a rolled-back report.
    trap = Ladder.published_delta(pre_window, post)
    assert trap is not None
    assert trap > 0

    # The fix: `_harmful_refresh` reports the post-quarantine rating/rd but
    # voids the move delta unconditionally — a rolled-back window sells nothing.
    refreshed_rating, refreshed_rd, refreshed_delta = loop._harmful_refresh()
    assert (refreshed_rating, refreshed_rd) == (post.rating, post.rd)
    assert refreshed_delta is None


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
