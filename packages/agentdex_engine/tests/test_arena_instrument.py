"""Phase-A5 — measurement instrument unit tests (A4/A8 anchors in code)."""

from __future__ import annotations

import random

import pytest
from agentdex_engine.modules.arena import (
    ChainError,
    EventLog,
    InvalidRatingEvent,
    Ladder,
    Rating,
    RatingEvent,
    battles_to_detect,
    elo_to_winprob,
    extract_signatures,
    load_patterns,
    mcnemar_verdict,
    power_table,
    recompute_ladder,
    window_verdict,
)

HASH = "ab" * 16


def _ev(p1: str, p2: str, winner: str, i: int = 0) -> RatingEvent:
    return RatingEvent(battle_id=f"b{i}", p1=p1, p2=p2, winner=winner, input_log_blake2b16=HASH)


# ---------- glicko / ladder ----------


def test_glicko_known_example_direction_and_rd_shrink():
    """Glickman's worked example shape: rating moves toward results, RD shrinks."""
    ladder = Ladder()
    for name in ("me", "a", "b", "c"):
        ladder.register(name)
    ladder._ratings["me"] = Rating(rating=1500, rd=200)
    ladder._ratings["a"] = Rating(rating=1400, rd=30)
    ladder._ratings["b"] = Rating(rating=1550, rd=100)
    ladder._ratings["c"] = Rating(rating=1700, rd=300)
    ladder.rate_period([_ev("me", "a", "me", 1), _ev("me", "b", "b", 2), _ev("me", "c", "c", 3)])
    me = ladder.rating("me")
    assert 1460 < me.rating < 1470, me  # Glickman example: ~1464.06
    assert 150 < me.rd < 155, me  # ~151.52


def test_ladder_rejects_event_without_inputlog_hash():
    ladder = Ladder()
    ladder.register("x")
    ladder.register("y")
    bad = RatingEvent(battle_id="b", p1="x", p2="y", winner="x", input_log_blake2b16="")
    with pytest.raises(InvalidRatingEvent, match="A2"):
        ladder.rate_period([bad])


def test_frozen_anchor_never_moves():
    ladder = Ladder()
    ladder.register("anchor", frozen=True)
    ladder.register("challenger")
    before = ladder.rating("anchor").model_copy()
    ladder.rate_period([_ev("challenger", "anchor", "challenger", i) for i in range(10)])
    assert ladder.rating("anchor") == before
    assert ladder.rating("challenger").rating > 1500


def test_published_delta_inconclusive_below_2rd():
    before = Rating(rating=1500, rd=80)
    small = Rating(rating=1530, rd=80)  # |30| < 160
    big = Rating(rating=1700, rd=80)
    assert Ladder.published_delta(before, small) is None
    assert Ladder.published_delta(before, big) == pytest.approx(200.0)


# ---------- power ----------


def test_power_table_matches_known_arithmetic():
    table = power_table()
    # 100 Elo -> p=0.64; ~96-100 battles at 80% power / alpha .05
    assert 90 <= table[100.0] <= 105, table
    assert table[400.0] <= 12
    assert table[25.0] > 700
    print(f"\nPOWER_TABLE: {table}")


def test_window_verdict_marks_underpowered_inconclusive():
    assert window_verdict(100.0, battles=20) == "INCONCLUSIVE"
    assert window_verdict(100.0, battles=120) == "POWERED"
    assert window_verdict(400.0, battles=12) == "POWERED"


def test_power_is_domain_generic():
    # any binary oracle: pass p directly, no Elo anywhere
    assert battles_to_detect(0.75) < battles_to_detect(0.60) < battles_to_detect(0.55)
    assert elo_to_winprob(0.0) == pytest.approx(0.5)


# ---------- paired (CRN/McNemar) ----------


def test_mcnemar_effective_and_harmful_and_inconclusive():
    eff = mcnemar_verdict([(True, False)] * 15 + [(False, True)] * 2 + [(True, True)] * 10)
    assert eff.verdict == "EFFECTIVE" and eff.p_value < 0.05
    harm = mcnemar_verdict([(False, True)] * 15 + [(True, False)] * 2)
    assert harm.verdict == "HARMFUL"
    inc = mcnemar_verdict([(True, False)] * 5 + [(False, True)] * 4)
    assert inc.verdict == "INCONCLUSIVE"
    concordant_only = mcnemar_verdict([(True, True)] * 30)
    assert concordant_only.verdict == "INCONCLUSIVE" and concordant_only.p_value == 1.0


# ---------- events / recompute (A8) ----------


def test_event_log_chain_and_byte_identical_recompute(tmp_path):
    path = tmp_path / "events.jsonl"
    elog = EventLog(path)
    elog.append("register", {"name": "anchor", "frozen": True})
    elog.append("register", {"name": "champ"})
    rng = random.Random(7)
    events = [
        _ev("champ", "anchor", "champ" if rng.random() < 0.7 else "anchor", i).model_dump()
        for i in range(30)
    ]
    elog.append("period", {"events": events})
    assert elog.verify_chain() == 3

    l1 = recompute_ladder(path)
    l2 = recompute_ladder(path)
    assert l1.entrants == l2.entrants, "recompute must be byte-identical"
    assert l1.rating("anchor").rating == 1500.0  # frozen
    assert l1.rating("champ").games == 30
    print(
        f"\nRECOMPUTE_PROOF: champ={l1.rating('champ').rating:.2f}±{l1.rating('champ').rd:.1f} "
        f"identical across two replays of {path.name}"
    )


def test_event_log_tamper_detected(tmp_path):
    path = tmp_path / "events.jsonl"
    elog = EventLog(path)
    elog.append("register", {"name": "a"})
    elog.append("register", {"name": "b"})
    lines = path.read_text().splitlines()
    lines[0] = lines[0].replace('"a"', '"hacked"')
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ChainError):
        EventLog(path).verify_chain()


def test_event_sync_failure_never_blocks_append(tmp_path):
    def bad_sync(event):
        raise ConnectionError("durable store down")

    elog = EventLog(tmp_path / "e.jsonl", sync=bad_sync)
    event = elog.append("register", {"name": "x"})
    assert event["seq"] == 0
    assert elog.verify_chain() == 1


# ---------- signatures ----------


def test_signatures_deterministic_and_side_scoped():
    lines = [
        "|move|p1a: Pika|Thunderbolt|p2a: Gyara",
        "|-immune|p2a: Gyara",  # wait, electric vs gyarados isn't immune — fixture only
        "|move|p2a: Gyara|Earthquake|p1a: Pika",
        "|-supereffective|p1a: Pika",
        "|faint|p1a: Pika",
        "|move|p1a: Mew|Psychic|p2a: Dark",
        "|-immune|p2a: Dark",
    ]
    sigs = extract_signatures(lines, side="p1")
    by_name = {s.signature: s for s in sigs}
    assert by_name["immune_move_clicked"].count == 2
    assert by_name["supereffective_taken"].count == 1
    assert by_name["mon_fainted"].count == 1
    assert extract_signatures(lines, side="p1") == sigs  # deterministic
    # p2's view: no immune clicks of its own
    assert "immune_move_clicked" not in {s.signature for s in extract_signatures(lines, side="p2")}


def test_patterns_yaml_is_the_enum():
    patterns = load_patterns()
    assert {"immune_move_clicked", "mon_fainted"} <= set(patterns)
    for sig in extract_signatures(["|move|p1a: A|X|p2a: B", "|-immune|p2a: B"], side="p1"):
        assert sig.signature in patterns
