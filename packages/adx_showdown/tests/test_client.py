"""Phase P1-b — adx-client state reducer (client.py).

Folds the typed protocol stream into one queryable BattleState. The golden log
is a real pokemon-showdown 0.11.10 gen9randombattle slice (turns 1-7), so the
expected final state is what the engine actually produced.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.client import BattleClient, BattleState, hp_pct_of, reduce, reduce_lines
from adx_showdown.lineproto import parse_stream

GOLDEN = Path(__file__).resolve().parent / "golden" / "arena" / "protocol_log_sample.txt"


def _golden_lines() -> list[str]:
    return GOLDEN.read_text(encoding="utf-8").splitlines()


def test_reduce_golden_log_final_state():
    state = reduce_lines(_golden_lines())
    assert state.turn_no == 7
    # p1: Azumarill + Arcanine fainted → Gardevoir freshly in at full HP
    assert state.p1.player_name == "Alpha"
    assert state.p1.team_size == 6
    assert state.p1.active_species == "Gardevoir"
    assert state.p1.hp_pct == 100
    assert state.p1.fainted_count == 2
    assert state.p1.remaining_pips == 4
    # p2: Lumineon fainted → Swampert in, healed to 60% by Leftovers
    assert state.p2.active_species == "Swampert"
    assert state.p2.hp_pct == 60
    assert state.p2.fainted_count == 1
    # battle still going
    assert state.winner is None and state.ended is False


def test_incremental_equals_batch_at_every_turn_boundary():
    events = parse_stream(_golden_lines())
    client = BattleClient()
    for i, ev in enumerate(events):
        client.apply(ev)
        if ev.type == "turn":
            batch = reduce(events[: i + 1])
            assert client.state.model_dump() == batch.model_dump(), (
                f"incremental != batch at turn {ev.turn_no}"
            )


def test_hp_changes_only_on_damage_events():
    base = [
        "|switch|p1a: Pika|Pikachu, L50, M|100/100",
        "|turn|1",
    ]
    # no damage yet → full HP
    assert reduce_lines(base).p1.hp_pct == 100
    # a -damage event moves it; nothing else does
    with_damage = base + ["|move|p2a: X|Tackle|p1a: Pika", "|-damage|p1a: Pika|55/100"]
    assert reduce_lines(with_damage).p1.hp_pct == 55
    # remove ONLY the -damage line → HP stays at 100 (no independent source)
    without = [ln for ln in with_damage if not ln.startswith("|-damage|")]
    assert reduce_lines(without).p1.hp_pct == 100


def test_boosts_track_and_reset_on_switch():
    lines = [
        "|switch|p1a: Mon|Garchomp, L78, M|100/100",
        "|-boost|p1a: Mon|atk|2",
        "|-unboost|p1a: Mon|spe|1",
    ]
    s = reduce_lines(lines)
    assert s.p1.boosts == {"atk": 2, "spe": -1}
    # a switch-in clears the previous mon's boosts (per-mon volatile)
    s2 = reduce_lines(lines + ["|switch|p1a: Other|Tyranitar, L80|100/100"])
    assert s2.p1.boosts == {}
    assert s2.p1.active_species == "Tyranitar"


def test_status_set_and_cleared():
    s = reduce_lines(["|switch|p1a: Mon|Jirachi, L80|100/100", "|-status|p1a: Mon|par"])
    assert s.p1.status == "par"
    s2 = reduce_lines(
        [
            "|switch|p1a: Mon|Jirachi, L80|100/100",
            "|-status|p1a: Mon|par",
            "|-curestatus|p1a: Mon|par",
        ]
    )
    assert s2.p1.status == ""


def test_win_and_tie():
    assert reduce_lines(["|win|Beta"]).winner == "Beta"
    assert reduce_lines(["|win|Beta"]).ended is True
    assert reduce_lines(["|tie"]).winner == ""
    assert reduce_lines(["|tie"]).ended is True


def test_reasoning_folded_by_turn():
    lines = [
        "|turn|1",
        "|-reasoning|p1|Lead with priority to deny the switch",
        "|move|p1a: X|Aqua Jet|p2a: Y",
        "|turn|2",
        "|-reasoning|p2|Pivot out before the boost lands",
    ]
    s = reduce_lines(lines)
    assert s.reasoning_by_turn[1]["p1"] == "Lead with priority to deny the switch"
    assert s.reasoning_by_turn[2]["p2"] == "Pivot out before the boost lands"


def test_formechange_updates_species_and_hp_without_resetting_volatiles():
    """A forme change is the SAME mon — species + HP update, but boosts persist
    (unlike a switch-in). PR #200 review 3431806055."""
    s = reduce_lines(
        [
            "|switch|p1a: Aegislash|Aegislash, L78|100/100",
            "|-boost|p1a: Aegislash|atk|2",
            "|-formechange|p1a: Aegislash|Aegislash-Blade|70/100",
        ]
    )
    assert s.p1.active_species == "Aegislash-Blade"
    assert s.p1.hp_pct == 70  # the HPSTATUS field was folded, not ignored
    assert s.p1.boosts == {"atk": 2}  # volatiles persist (not a switch-in)


def test_empty_input_is_empty_state_not_crash():
    s = reduce([])
    assert isinstance(s, BattleState)
    assert s.turn_no == 0 and s.winner is None and s.p1.hp_pct == 100


def test_hp_pct_parsing_edge_cases():
    assert hp_pct_of("298/298") == 100
    assert hp_pct_of("176/298") == 60  # ceil(partial) → matches public 60/100
    assert hp_pct_of("60/100") == 60  # exact % not over-rounded (float-safe ceil)
    assert hp_pct_of("55/100") == 55  # 55.00000000000001 must not become 56
    assert hp_pct_of("0 fnt") == 0
    assert hp_pct_of("264/291 par") == 91  # status suffix ignored for HP
    assert hp_pct_of("garbage") == 100  # never crashes


def test_status_carried_in_switch_in_hpstatus():
    """A statused mon switching back in re-states its condition in the HPSTATUS
    suffix (no fresh |-status|), and boosts still reset. PR #208 review."""
    s = reduce_lines(
        [
            "|switch|p1a: Gren|Greninja, L78|100/100",
            "|-status|p1a: Gren|brn",
            "|-boost|p1a: Gren|spe|2",
            "|switch|p1a: Other|Ferrothorn, L80|100/100",  # bench in, no status
            "|switch|p1a: Gren|Greninja, L78|60/100 brn",  # statused mon back in
        ]
    )
    assert s.p1.status == "brn"  # carried by the HPSTATUS suffix on switch-in
    assert s.p1.boosts == {}  # boosts are volatile — reset on switch


def test_clearallboost_clears_both_sides():
    s = reduce_lines(
        [
            "|switch|p1a: A|Garchomp, L78|100/100",
            "|switch|p2a: B|Tyranitar, L80|100/100",
            "|-boost|p1a: A|atk|2",
            "|-boost|p2a: B|def|1",
            "|-clearallboost",  # Haze
        ]
    )
    assert s.p1.boosts == {} and s.p2.boosts == {}


def test_terrain_field_start_and_end():
    s = reduce_lines(["|-fieldstart|move: Grassy Terrain"])
    assert s.field.get("Grassy Terrain") == "active"
    s2 = reduce_lines(["|-fieldstart|move: Grassy Terrain", "|-fieldend|move: Grassy Terrain"])
    assert "Grassy Terrain" not in s2.field


def test_replace_updates_active_species():
    # Zoroark illusion ends → the revealed true mon
    s = reduce_lines(
        ["|switch|p1a: X|Zoroark, L78|100/100", "|replace|p1a: X|Zoroark, L78|100/100"]
    )
    assert s.p1.active_species == "Zoroark"


def test_revival_blessing_decrements_fainted_count_not_active_hp():
    """Revival Blessing is the ONLY heal Showdown aims at a fainted BENCH mon:
    `|-heal|pX: Mon|HP|[from] move: Revival Blessing` (pinned sim/battle.ts:2738).
    It must decrement fainted_count (so remaining_pips recovers) and must NOT
    overwrite the active mon's hp_pct with the revived bench mon's HP. The old
    `_on_heal = _on_damage` alias did the opposite. PR #208 review 3432027338."""
    s = reduce_lines(
        [
            "|switch|p1a: Sneasler|Sneasler, L78|100/100",
            "|faint|p1a: Sneasler",  # active faints → fainted_count=1
            "|switch|p1a: Garchomp|Garchomp, L78|80/100",  # new active at 80%
            "|-heal|p1: Sneasler|50/100|[from] move: Revival Blessing",  # revive bench
        ]
    )
    assert s.p1.fainted_count == 0  # revival recovered the pip
    assert s.p1.hp_pct == 80  # active Garchomp HP NOT clobbered by the bench 50%


def test_ordinary_heal_still_folds_active_hp():
    """A normal |-heal| (Leftovers, drain, etc.) targets the active mon and must
    still update hp_pct — the Revival Blessing carve-out must not regress it."""
    s = reduce_lines(
        [
            "|switch|p1a: Toxapex|Toxapex, L80|50/100",
            "|-heal|p1a: Toxapex|56/100|[from] item: Leftovers",
        ]
    )
    assert s.p1.hp_pct == 56


def test_replace_preserves_boosts_on_illusion_reveal():
    """An Illusion reveal (|replace|) is the SAME active mon unmasked — it did NOT
    switch out, so boosts gained while disguised (e.g. Nasty Plot) must survive the
    reveal. Routing replace through _on_switch wiped them. PR #216 review 3432167183."""
    s = reduce_lines(
        [
            "|switch|p1a: Decoy|Zoroark, L84, M|100/100",  # disguised as a teammate
            "|-boost|p1a: Decoy|spa|2",  # Nasty Plot while disguised
            "|-damage|p1a: Decoy|70/100",
            "|replace|p1a: Zoroark|Zoroark, L84, M|70/100",  # illusion breaks
        ]
    )
    assert s.p1.active_species == "Zoroark"  # revealed identity folded
    assert s.p1.active_nickname == "Zoroark"  # nickname updated to the true mon
    assert s.p1.hp_pct == 70  # HP carried, not reset to a fresh 100
    assert s.p1.boosts == {"spa": 2}  # volatile boosts SURVIVE the reveal (the fix)


def test_unknown_events_are_safe_noops():
    # a malformed / unknown type must not crash the fold (digest §7)
    s = reduce_lines(["|turn|1", "|totallymadeup|x|y", "|-neverseen|p1a: Z"])
    assert s.turn_no == 1


def test_battlestate_is_strict():
    # extra fields forbidden — the state is a closed, audited shape
    import pytest

    with pytest.raises(Exception):
        BattleState(turn_no=1, bogus="x")  # type: ignore[call-arg]
