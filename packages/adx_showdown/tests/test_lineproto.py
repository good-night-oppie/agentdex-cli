"""Phase P1-a — typed line-protocol parser (lineproto.py).

Ground-truthed against pokemon-showdown 0.11.10 output (the pinned sidecar
version). Lines below are copied verbatim from a real gen9randombattle capture,
so the parser is tested against what Showdown actually emits — not a paraphrase.
"""

from __future__ import annotations

from adx_showdown.lineproto import (
    DIVIDER_TYPE,
    MESSAGE_TYPES,
    NONDETERMINISTIC_TYPES,
    REASONING_TYPE,
    PokemonIdent,
    ProtocolEvent,
    Tier,
    is_section_break,
    parse_line,
    parse_stream,
    tier_of,
)


def test_move_is_major_with_sanitized_idents():
    ev = parse_line("|move|p1a: Garchomp|Earthquake|p2a: Skarmory")
    assert ev.type == "move"
    assert ev.tier is Tier.MAJOR
    assert list(ev.args) == ["p1a: Garchomp", "Earthquake", "p2a: Skarmory"]
    # idents parsed + sanitized; numeric/move args untouched
    assert [i.name for i in ev.idents] == ["Garchomp", "Skarmory"]
    assert ev.idents[0].side == "p1" and ev.idents[0].position == "a"
    assert ev.raw == "|move|p1a: Garchomp|Earthquake|p2a: Skarmory"  # faithful


def test_damage_is_minor_and_hp_arg_is_verbatim():
    ev = parse_line("|-damage|p2a: Skarmory|45/100")
    assert ev.type == "-damage"
    assert ev.tier is Tier.MINOR
    # HP string preserved verbatim — sanitizing it would strip the '/'
    assert list(ev.args) == ["p2a: Skarmory", "45/100"]
    assert ev.lane == "indent-red"


def test_turn_carries_turn_no_and_is_major():
    ev = parse_line("|turn|3")
    assert ev.type == "turn" and ev.tier is Tier.MAJOR
    assert ev.turn_no == 3
    assert is_section_break(ev)


def test_bare_pipe_is_meta_divider():
    ev = parse_line("|")
    assert ev.type == DIVIDER_TYPE == ""
    assert ev.tier is Tier.META
    assert is_section_break(ev)


def test_kwargs_from_and_of_populated():
    ev = parse_line("|-ability|p1a: Gardevoir|Torrent|[from] ability: Trace|[of] p2a: Swampert")
    assert ev.type == "-ability" and ev.tier is Tier.MINOR
    assert list(ev.args) == ["p1a: Gardevoir", "Torrent"]  # positionals stop at first kwarg
    assert ev.kwargs == {"from": "ability: Trace", "of": "p2a: Swampert"}


def test_flag_kwarg_and_blank_positional_preserved():
    # |move|src|Protect||[still] — blank target positional + flag-only kwarg
    ev = parse_line("|move|p2a: Trevenant|Protect||[still]")
    assert list(ev.args) == ["p2a: Trevenant", "Protect", ""]
    assert ev.kwargs == {"still": ""}


def test_damage_with_from_item_kwarg():
    ev = parse_line("|-damage|p2a: Lumineon|252/279|[from] item: Life Orb")
    assert list(ev.args) == ["p2a: Lumineon", "252/279"]
    assert ev.kwargs == {"from": "item: Life Orb"}


def test_switch_arg_order_details_and_hp():
    ev = parse_line("|switch|p1a: Azumarill|Azumarill, L82, M|298/298")
    assert ev.type == "switch" and ev.tier is Tier.MAJOR
    assert list(ev.args) == ["p1a: Azumarill", "Azumarill, L82, M", "298/298"]


def test_win_and_status_and_cant_lines():
    assert parse_line("|win|Beta").type == "win"
    assert parse_line("|win|Beta").tier is Tier.MAJOR
    st = parse_line("|-status|p1a: Jirachi|par")
    assert (
        st.type == "-status" and st.tier is Tier.MINOR and list(st.args) == ["p1a: Jirachi", "par"]
    )
    cant = parse_line("|cant|p1a: Jirachi|par")
    assert cant.type == "cant" and cant.tier is Tier.MAJOR  # no hyphen


def test_split_is_meta_secret_share_marker():
    ev = parse_line("|split|p1")
    assert ev.type == "split" and ev.tier is Tier.META
    assert list(ev.args) == ["p1"]


def test_timestamp_is_nondeterministic_meta():
    ev = parse_line("|t:|1781733436")
    assert ev.type == "t:" and ev.tier is Tier.META
    assert ev.is_nondeterministic
    assert ev.type in NONDETERMINISTIC_TYPES


def test_unknown_type_never_raises_and_tiers_by_hyphen():
    major = parse_line("|totallymadeup|x|y")
    assert major.type == "totallymadeup" and major.tier is Tier.MAJOR
    minor = parse_line("|-neverbeforeseen|p1a: X")
    assert minor.type == "-neverbeforeseen" and minor.tier is Tier.MINOR
    # malformed-ish input still yields an event, never an exception
    assert parse_line("").type == ""
    assert parse_line("no leading pipe").type == "no leading pipe"


def test_reasoning_is_a_first_class_added_minor():
    ev = parse_line("|-reasoning|p1|Lead with priority to deny the switch")
    assert ev.type == REASONING_TYPE and ev.tier is Tier.MINOR
    assert ev.lane == "reasoning"
    assert ev.args[0] == "p1"


def test_parse_stream_assigns_monotonic_index_and_is_pure():
    lines = [
        "|turn|1",
        "|move|p1a: Azumarill|Aqua Jet|p2a: Lumineon",
        "|-damage|p1a: Azumarill|60/100",
        "|",
        "|upkeep",
    ]
    a = parse_stream(lines)
    b = parse_stream(lines)
    assert [e.index for e in a] == [0, 1, 2, 3, 4]
    # pure: identical structured output for identical input
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]
    # turn anchor present, divider present
    assert a[0].turn_no == 1
    assert a[3].type == DIVIDER_TYPE


def test_ident_sanitizes_injection_nickname_but_keeps_raw():
    payload = "p1a: Pika|/forfeit<script>"
    # an injected nickname would arrive split across pipes in practice, but the
    # ident parser must still strip metacharacters from whatever reaches it.
    ident = PokemonIdent.parse("p2a: Evil|Name")
    assert "|" not in ident.name and ident.side == "p2"
    ev = parse_line("|switch|" + payload + "|Pikachu, L82, M|100/100")
    # raw is faithful; any rendered ident name is sanitized
    assert ev.raw.startswith("|switch|p1a: Pika|/forfeit")
    assert all("|" not in i.name and "<" not in i.name for i in ev.idents)


def test_every_registry_entry_has_consistent_tier():
    # the registry is the documented set; tier_of must agree with it
    for mtype, spec in MESSAGE_TYPES.items():
        assert tier_of(mtype) is spec.tier, f"{mtype}: registry/tier_of disagree"


def test_protocol_doc_covers_registry():
    """The published protocol doc MUST enumerate every MESSAGE_TYPES entry.

    Criterion: "every event type in MESSAGE_TYPES is documented in the protocol
    doc." We assert the doc table contains a row for each registry key so the
    doc and code can never silently drift.
    """
    from pathlib import Path

    # tests/ -> adx_showdown/ -> packages/ -> repo root
    repo_root = Path(__file__).resolve().parents[3]
    doc = repo_root / "docs" / "references" / "2026-06-17-arena-line-protocol.md"
    assert doc.exists(), f"protocol doc missing at {doc}"
    text = doc.read_text(encoding="utf-8")
    missing = []
    for mtype in MESSAGE_TYPES:
        token = "`|`" if mtype == "" else f"`|{mtype}|`"
        if token not in text:
            missing.append(mtype or "<divider>")
    assert not missing, f"protocol doc missing rows for: {missing}"


def test_request_json_payload_kept_intact_with_pipes():
    """A |request| payload is opaque JSON that can contain pipes inside an
    opponent nickname/move name (red-team corpus: Pika|/forfeit). It must NOT be
    split on every pipe, or downstream parse_request sees truncated invalid JSON.
    PR #200 review 3431806042.
    """
    import json

    from adx_showdown.protocol import parse_request

    raw = (
        '|request|{"active":[{"moves":[{"move":"Iron|/Tail<inject>","id":"irontail",'
        '"pp":24,"maxpp":24}]}],"side":{"name":"Pika|/forfeit","id":"p1","pokemon":['
        '{"ident":"p1: Pika|/forfeit","details":"Pikachu, L50, M","condition":"100/100",'
        '"active":true}]},"rqid":3}'
    )
    ev = parse_line(raw)
    assert ev.type == "request"
    assert len(ev.args) == 1, "payload must stay a single opaque field"
    payload = json.loads(ev.args[0])  # still valid JSON despite the inner pipes
    assert payload["side"]["name"] == "Pika|/forfeit"
    # and the existing request parser consumes it + sanitizes the nickname
    req = parse_request(ev.args[0])
    assert req.rqid == 3
    assert "|" not in req.bench[0].name


def test_empty_request_payload():
    ev = parse_line("|request|")
    assert ev.type == "request" and list(ev.args) == [""]


def test_kwarg_idents_are_sanitized():
    """An opponent ident inside a kwarg ([of] p2a: <nick>) must be sanitized in
    both ev.idents AND the kwarg value — no A6 bypass. PR #200 review 3431806028.
    """
    ev = parse_line("|-ability|p1a: Gardevoir|Trace|[from] ability: Trace|[of] p2a: Swampert")
    of_idents = [i for i in ev.idents if i.side == "p2"]
    assert of_idents and of_idents[0].name == "Swampert"
    assert ev.kwargs["of"] == "p2a: Swampert"
    assert ev.kwargs["from"] == "ability: Trace"  # an effect, not an ident — verbatim

    # injection case: a markup nickname in [of] is stripped everywhere consumable
    ev2 = parse_line("|-damage|p1a: X|50/100|[from] move: Tackle|[of] p2a: Evil<script>Name")
    assert all("<" not in i.name for i in ev2.idents)
    assert "<script>" not in ev2.kwargs["of"]
    assert ev2.raw.endswith("Evil<script>Name")  # raw stays faithful for hashing


def test_normal_lines_still_split_after_opaque_change():
    # the opaque carve-out must not affect ordinary pipe-delimited messages
    ev = parse_line("|move|p1a: Garchomp|Earthquake|p2a: Skarmory")
    assert list(ev.args) == ["p1a: Garchomp", "Earthquake", "p2a: Skarmory"]


def test_event_sequence_fields_are_immutable_tuples():
    """args + idents are tuples so a downstream reducer can't mutate the shared
    parsed log in place. PR #200 review 3431806033.
    """
    import pytest

    ev = parse_line("|-ability|p1a: X|Trace|[of] p2a: Y")
    assert isinstance(ev.args, tuple)
    assert isinstance(ev.idents, tuple)
    with pytest.raises(AttributeError):
        ev.args.append("boom")  # type: ignore[attr-defined]


def test_event_is_frozen_and_strict():
    ev = parse_line("|turn|1")
    assert isinstance(ev, ProtocolEvent)
    # frozen — events are immutable folds
    try:
        ev.type = "mutated"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("ProtocolEvent should be frozen")
