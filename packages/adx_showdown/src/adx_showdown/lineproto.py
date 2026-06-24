"""Typed Showdown line-protocol — the single battle wire format (digest P1-a).

Per the 2026-06-17 Human-vs-AI UX digest §2: the engine emits an append-only
``|TYPE|args|[kwargs]`` line stream and every renderer (TUI, web, replay) is a
*pure reducer* over it. Live play and replay then share one render path. The
hyphen-prefix is the **tier signal** — it is, in the digest's words, "the
renderer's animation-lane router":

- **major** (``|turn|``, ``|move|``, ``|switch|``, ``|faint|``, ``|win|``) —
  structures turns; rendered as headline lines.
- **minor** (``|-damage|``, ``|-boost|``, ``|-status|``, ``|-reasoning|``) —
  consequences animated *underneath* the major they follow; indented.
- **meta** (the bare ``|`` divider, ``|t:|`` timestamps, ``|player|``,
  ``|split|``, ``|upkeep|`` …) — preamble / section-dividers / housekeeping.

This module owns *nothing* about presentation (adx-view does that) and *nothing*
about the engine (adx-sim does that). It is the typed boundary both sides fold
over — the @pkmn ``Protocol.parse`` model ported to Python.

Two cross-cutting protocol facts, ground-truthed against ``pokemon-showdown``
0.11.10 (the pinned sidecar version), that downstream phases depend on:

- ``|split|SIDE`` is Showdown's **secret-sharing** marker: the line *after* it is
  the private (full-HP, e.g. ``176/298``) view shown only to ``SIDE``; the line
  after that is the public (percentage, ``60/100``) view shown to everyone else.
  This is the native fog-of-war primitive the perspective-multiplexing phase
  (digest §4) routes on. See :data:`SPLIT_TYPE`.
- ``|t:|<unixtime>`` lines are **non-deterministic** wall-clock stamps. The
  ``(seed, inputLog)`` verify path (digest §1) must strip them before hashing —
  see :data:`NONDETERMINISTIC_TYPES`.

Faithfulness contract: :attr:`ProtocolEvent.raw` is the verbatim line and is
never mutated, so the protocol log round-trips for re-simulation hashing. The
A6 sanitizer (``[A-Za-z0-9 _-]`` allowlist) is applied to the one
opponent-controlled free-text field — the nickname inside a Pokémon ident
(:class:`PokemonIdent`) — wherever it appears: positional args AND ident-shaped
kwarg values (``[of] p2a: <nick>``). Numeric/structural args (HP ``176/298``)
and non-ident effect kwargs (``[from] item: Life Orb``) stay verbatim.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.protocol import sanitize_name


class Tier(StrEnum):
    """Render-lane tier derived from the hyphen-prefix convention."""

    MAJOR = "major"
    MINOR = "minor"
    META = "meta"


# --- the divider / special meta sentinels -----------------------------------

DIVIDER_TYPE = ""  # a bare ``|`` line — the protocol-level turn/section break
TIMESTAMP_TYPE = "t:"
SPLIT_TYPE = "split"

#: Types whose payload is wall-clock / environment-dependent and MUST be
#: excluded from any determinism hash (digest P1-c verify path).
NONDETERMINISTIC_TYPES: frozenset[str] = frozenset({TIMESTAMP_TYPE})

#: agentdex's ADDED minor — not emitted by Showdown. Carries the trainer-agent's
#: rationale on the same ordered timeline as its move (digest §3, P1-d). Listed
#: here so the tier table + renderers treat it as a first-class minor.
REASONING_TYPE = "-reasoning"
SAY_TYPE = "say"

#: Types whose payload ends in a single OPAQUE field (JSON / HTML / free text)
#: that may itself contain ``|`` — splitting it on every pipe corrupts it (e.g. a
#: ``|request|`` JSON carrying an opponent nickname ``Pika|/forfeit`` truncates to
#: invalid JSON, and the guided action pane could not ``parse_request`` it). The
#: value is the count of LEADING structured ``|``-delimited fields BEFORE the
#: opaque tail: 0 = the whole remainder is opaque (``|request|JSON``); 1 =
#: ``|uhtml|NAME|HTML`` / ``|c|USER|MESSAGE`` (keep NAME/USER, opaque rest); 2 =
#: ``|c:|TIMESTAMP|USER|MESSAGE``. Only the final field stays opaque, so a reducer
#: can still attribute chat/uhtml by speaker (PR #209 review).
OPAQUE_PAYLOAD_TYPES: dict[str, int] = {
    "request": 0,
    "raw": 0,
    "html": 0,
    # The sidecar augments captured |error| control lines with the parsed side as
    # `|error|<side>|<message>` (sideupdate errors are pure text with no side of
    # their own — PR #214 review). lead=1 keeps <side> structured and the message
    # opaque; a bare Showdown |error|TEXT (no pipe in TEXT) still degrades to a
    # single arg, so the change is back-compatible.
    "error": 1,
    "inactive": 0,
    "inactiveoff": 0,
    "message": 0,
    "-message": 0,
    "popup": 0,
    "bigerror": 0,
    "debug": 0,
    "uhtml": 1,  # |uhtml|NAME|HTML
    "uhtmlchange": 1,  # |uhtmlchange|NAME|HTML
    "chat": 1,  # |chat|USER|MESSAGE
    "c": 1,  # |c|USER|MESSAGE
    "c:": 2,  # |c:|TIMESTAMP|USER|MESSAGE
    REASONING_TYPE: 1,  # |-reasoning|SIDE|TEXT
    SAY_TYPE: 1,  # |say|SIDE|TEXT
}


class _Spec(BaseModel):
    model_config = ConfigDict(frozen=True)
    tier: Tier
    arg_order: str
    lane: str
    note: str = ""


def _spec(tier: Tier, arg_order: str, lane: str, note: str = "") -> _Spec:
    return _Spec(tier=tier, arg_order=arg_order, lane=lane, note=note)


# --- the documented message-set registry ------------------------------------
# Curated tiers/arg-orders for the well-known battle messages. Anything NOT in
# here still parses (never raises) and is tiered by the hyphen rule in
# :func:`tier_of`. Arg orders use UPPERCASE placeholders; POKEMON is a
# ``pXa: Nickname`` ident, HPSTATUS is ``cur/max`` or ``0 fnt`` or ``cur/max sta``.
# Ground-truthed against pokemon-showdown 0.11.10 + the @pkmn/protocol catalog.
MESSAGE_TYPES: dict[str, _Spec] = {
    # majors — structure the turn timeline
    "turn": _spec(Tier.MAJOR, "N", "rule", "turn boundary; carries turn_no"),
    "move": _spec(Tier.MAJOR, "POKEMON|MOVE|TARGET", "headline", "agent action"),
    "switch": _spec(Tier.MAJOR, "POKEMON|DETAILS|HPSTATUS", "headline", "loadout swap-in"),
    "drag": _spec(Tier.MAJOR, "POKEMON|DETAILS|HPSTATUS", "headline", "forced switch-in"),
    "faint": _spec(Tier.MAJOR, "POKEMON", "headline", "unit eliminated"),
    "win": _spec(Tier.MAJOR, "WINNER", "headline", "battle end — winner name"),
    "tie": _spec(Tier.MAJOR, "", "headline", "battle end — draw"),
    "cant": _spec(Tier.MAJOR, "POKEMON|REASON|MOVE", "headline", "action prevented"),
    "swap": _spec(Tier.MAJOR, "POKEMON|POSITION", "headline", "slot swap"),
    "replace": _spec(Tier.MAJOR, "POKEMON|DETAILS|HPSTATUS", "headline", "illusion reveal"),
    "detailschange": _spec(Tier.MAJOR, "POKEMON|DETAILS|HPSTATUS", "headline", "permanent forme"),
    "start": _spec(Tier.MAJOR, "", "headline", "battle start (after preamble + divider)"),
    "message": _spec(Tier.MAJOR, "TEXT", "headline", "engine narration line"),
    # agentdex-added minor — rationale lane
    REASONING_TYPE: _spec(Tier.MINOR, "SIDE|TEXT", "reasoning", "agentdex trainer rationale"),
    SAY_TYPE: _spec(Tier.MINOR, "SIDE|TEXT", "reasoning", "agentdex/persona chatter"),
    # minors — consequences animated underneath their parent major
    "-damage": _spec(Tier.MINOR, "POKEMON|HPSTATUS", "indent-red", "HP loss"),
    "-heal": _spec(Tier.MINOR, "POKEMON|HPSTATUS", "indent-green", "HP gain"),
    "-sethp": _spec(Tier.MINOR, "POKEMON|HPSTATUS", "indent", "HP set"),
    "-status": _spec(Tier.MINOR, "POKEMON|STATUS", "indent", "status inflicted (par/brn/…)"),
    "-curestatus": _spec(Tier.MINOR, "POKEMON|STATUS", "indent", "status cured"),
    "-boost": _spec(Tier.MINOR, "POKEMON|STAT|AMOUNT", "indent", "stat raised"),
    "-unboost": _spec(Tier.MINOR, "POKEMON|STAT|AMOUNT", "indent", "stat lowered"),
    "-setboost": _spec(Tier.MINOR, "POKEMON|STAT|AMOUNT", "indent", "stat set"),
    "-swapboost": _spec(Tier.MINOR, "SOURCE|TARGET|STATS", "indent", "boosts swapped"),
    "-invertboost": _spec(Tier.MINOR, "POKEMON", "indent", "boosts inverted"),
    "-clearboost": _spec(Tier.MINOR, "POKEMON", "indent", "all boosts cleared"),
    "-clearallboost": _spec(Tier.MINOR, "", "indent", "every side's boosts cleared"),
    "-clearpositiveboost": _spec(
        Tier.MINOR, "TARGET|POKEMON|EFFECT", "indent", "TARGET first — cleared mon"
    ),
    "-clearnegativeboost": _spec(Tier.MINOR, "POKEMON", "indent", "negative boosts cleared"),
    "-copyboost": _spec(Tier.MINOR, "SOURCE|TARGET", "indent", "boosts copied"),
    "-restoreboost": _spec(Tier.MINOR, "POKEMON", "indent", "boosts restored (Z-move)"),
    "-terastallize": _spec(Tier.MINOR, "POKEMON|TYPE", "indent", "Terastallization"),
    "-block": _spec(Tier.MINOR, "POKEMON|EFFECT", "indent", "move blocked"),
    "-notarget": _spec(Tier.MINOR, "POKEMON", "indent", "no target"),
    "-center": _spec(Tier.MINOR, "", "indent", "triples recenter"),
    "-ohko": _spec(Tier.MINOR, "", "indent", "one-hit KO"),
    "-combine": _spec(Tier.MINOR, "", "indent", "moves combined"),
    "-waiting": _spec(Tier.MINOR, "SOURCE|TARGET", "indent", "waiting (Bide etc.)"),
    "-zpower": _spec(Tier.MINOR, "POKEMON", "indent", "Z-power surge"),
    "-zbroken": _spec(Tier.MINOR, "POKEMON", "indent", "Z-protect broken"),
    "-hitcount": _spec(Tier.MINOR, "POKEMON|NUM", "indent", "multi-hit count"),
    "-fieldactivate": _spec(Tier.MINOR, "EFFECT", "indent", "pseudo-weather activate"),
    "-hint": _spec(Tier.MINOR, "MESSAGE", "indent", "rules hint"),
    "-anim": _spec(Tier.MINOR, "POKEMON|MOVE|TARGET", "indent", "animation-only"),
    "-crit": _spec(Tier.MINOR, "POKEMON", "indent-red", "critical hit"),
    "-supereffective": _spec(Tier.MINOR, "POKEMON", "indent", "super-effective"),
    "-resisted": _spec(Tier.MINOR, "POKEMON", "indent", "resisted"),
    "-immune": _spec(Tier.MINOR, "POKEMON", "indent", "immune"),
    "-miss": _spec(Tier.MINOR, "SOURCE|TARGET", "indent", "attack missed"),
    "-fail": _spec(Tier.MINOR, "POKEMON|ACTION", "indent", "action failed"),
    "-ability": _spec(Tier.MINOR, "POKEMON|ABILITY", "indent", "ability revealed/triggered"),
    "-endability": _spec(Tier.MINOR, "POKEMON", "indent", "ability suppressed"),
    "-item": _spec(Tier.MINOR, "POKEMON|ITEM", "indent", "item revealed"),
    "-enditem": _spec(Tier.MINOR, "POKEMON|ITEM", "indent", "item consumed/removed"),
    "-activate": _spec(Tier.MINOR, "POKEMON|EFFECT", "indent", "effect activated (e.g. Protect)"),
    "-start": _spec(Tier.MINOR, "POKEMON|EFFECT", "indent", "volatile started"),
    "-end": _spec(Tier.MINOR, "POKEMON|EFFECT", "indent", "volatile ended"),
    "-singleturn": _spec(Tier.MINOR, "POKEMON|MOVE", "indent", "single-turn effect (Protect)"),
    "-singlemove": _spec(Tier.MINOR, "POKEMON|MOVE", "indent", "single-move effect"),
    "-mustrecharge": _spec(Tier.MINOR, "POKEMON", "indent", "must recharge next turn"),
    "-prepare": _spec(Tier.MINOR, "POKEMON|MOVE", "indent", "two-turn move charge"),
    "-weather": _spec(Tier.MINOR, "WEATHER", "indent", "weather set/upkeep"),
    "-fieldstart": _spec(Tier.MINOR, "EFFECT", "indent", "field effect started"),
    "-fieldend": _spec(Tier.MINOR, "EFFECT", "indent", "field effect ended"),
    "-sidestart": _spec(Tier.MINOR, "SIDE|EFFECT", "indent", "side condition started"),
    "-sideend": _spec(Tier.MINOR, "SIDE|EFFECT", "indent", "side condition ended"),
    "-formechange": _spec(Tier.MINOR, "POKEMON|SPECIES|HPSTATUS", "indent", "temporary forme"),
    "-transform": _spec(Tier.MINOR, "POKEMON|TARGET", "indent", "Transform"),
    "-message": _spec(Tier.MINOR, "TEXT", "indent", "engine message"),
    # metas — preamble / dividers / housekeeping / secret-sharing / timestamps
    DIVIDER_TYPE: _spec(Tier.META, "", "rule", "bare | — section/turn divider"),
    TIMESTAMP_TYPE: _spec(Tier.META, "UNIXTIME", "hidden", "NON-DETERMINISTIC wall clock"),
    SPLIT_TYPE: _spec(Tier.META, "SIDE", "hidden", "secret-share: next=private, then=public"),
    "gametype": _spec(Tier.META, "GAMETYPE", "hidden", "singles/doubles"),
    "player": _spec(Tier.META, "SIDE|NAME|AVATAR|RATING", "hidden", "player intro"),
    "teamsize": _spec(Tier.META, "SIDE|SIZE", "rule", "public roster cardinality"),
    "gen": _spec(Tier.META, "NUM", "hidden", "generation"),
    "tier": _spec(Tier.META, "FORMAT", "hidden", "format name"),
    "rule": _spec(Tier.META, "RULE", "hidden", "clause announcement"),
    "clearpoke": _spec(Tier.META, "", "hidden", "team-preview clear"),
    "poke": _spec(Tier.META, "SIDE|DETAILS|ITEM", "hidden", "team-preview entry"),
    "teampreview": _spec(Tier.META, "", "hidden", "team-preview start"),
    "updatepoke": _spec(Tier.META, "POKEMON|DETAILS", "hidden", "team-preview detail reveal"),
    "rated": _spec(Tier.META, "MESSAGE", "hidden", "rated-battle marker"),
    "seed": _spec(Tier.META, "SEED", "hidden", "PRNG seed echo"),
    "badge": _spec(Tier.META, "SIDE|TYPE|FORMAT|VALUE", "hidden", "ladder-season badge"),
    "upkeep": _spec(Tier.META, "", "hidden", "end-of-turn housekeeping; ordering meaningful"),
    "done": _spec(Tier.META, "", "hidden", "request resolved"),
    "request": _spec(Tier.META, "JSON", "hidden", "decision request (see protocol.py)"),
    "inactive": _spec(Tier.META, "TEXT", "hidden", "timer message"),
    "inactiveoff": _spec(Tier.META, "TEXT", "hidden", "timer off"),
    "error": _spec(Tier.META, "SIDE|TEXT", "hidden", "rejected choice, sidecar-tagged with side"),
}


_IDENT_RE = re.compile(r"^(p[1-9])([a-z]?):\s*(.*)$")
_KWARG_RE = re.compile(r"^\[([a-z0-9]+)\]\s?(.*)$", re.IGNORECASE)


class PokemonIdent(BaseModel):
    """A ``pXa: Nickname`` protocol ident, with the nickname sanitized (A6).

    The nickname is the ONLY opponent-controlled free-text field in the wire
    protocol; in a visiting-agent battle it can carry an injection payload, so
    it is sanitized the moment it is parsed. :attr:`raw` keeps the verbatim
    token for faithful re-emission.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    raw: str
    side: str = ""  # 'p1' / 'p2' / '' if unparseable
    position: str = ""  # 'a' / 'b' (slot letter in doubles) / ''
    name: str = ""  # SANITIZED nickname/species

    @classmethod
    def parse(cls, token: str) -> PokemonIdent:
        m = _IDENT_RE.match(token.strip())
        if not m:
            return cls(raw=token, side="", position="", name=sanitize_name(token))
        side, pos, nick = m.group(1), m.group(2), m.group(3)
        return cls(raw=token, side=side, position=pos, name=sanitize_name(nick))


class ProtocolEvent(BaseModel):
    """One parsed ``|TYPE|args|[kwargs]`` line, tier-tagged.

    :attr:`raw` is verbatim (faithful for re-sim hashing); :attr:`args` are the
    raw positional args (HP strings etc. preserved); :attr:`idents` exposes the
    sanitized Pokémon idents found in the positional args + ident-shaped kwargs.

    The sequence fields are **tuples**, not lists: ``frozen=True`` only blocks
    field *reassignment*, so a ``list``/``dict`` could still be mutated in place
    (``ev.args.append(...)``) and corrupt the shared parsed log a reducer folds
    over. Tuples make :attr:`args`/:attr:`idents` immutable. ``kwargs`` stays a
    ``dict`` for ``parse_request`` ergonomics; it is built fresh per line (never
    shared across events) and the model is frozen, so callers must treat it as
    read-only. (PR #200 review 3431806033.)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    raw: str
    type: str
    tier: Tier
    args: tuple[str, ...] = ()
    kwargs: dict[str, str] = Field(default_factory=dict)
    idents: tuple[PokemonIdent, ...] = ()
    index: int = -1  # position in the stream; assigned by parse_stream
    turn_no: int | None = None  # set for |turn|N

    @property
    def is_nondeterministic(self) -> bool:
        """True for lines that must be stripped before a determinism hash."""
        return self.type in NONDETERMINISTIC_TYPES

    @property
    def is_divider(self) -> bool:
        """True only for the real bare ``|`` section divider (``raw == "|"``).

        Distinguishes it from an empty ``""`` line, which parses to the same
        empty *type* but is not a Showdown-emitted divider.
        """
        return self.raw == "|"

    @property
    def is_empty(self) -> bool:
        """True for a stray empty line (``raw == ""``) — not a real protocol event."""
        return self.raw == ""

    @property
    def lane(self) -> str:
        """Render lane hint from the registry (falls back by tier)."""
        spec = MESSAGE_TYPES.get(self.type)
        if spec is not None:
            return spec.lane
        return {"major": "headline", "minor": "indent", "meta": "hidden"}[self.tier.value]


def tier_of(msg_type: str) -> Tier:
    """Tier for a message type: registry first, then the hyphen rule.

    The hyphen-prefix is the load-bearing signal (digest §2): an unknown
    ``-foo`` minor still routes to the indent lane; an unknown bare type is a
    major. Empty type is the meta divider.
    """
    spec = MESSAGE_TYPES.get(msg_type)
    if spec is not None:
        return spec.tier
    if msg_type == DIVIDER_TYPE:
        return Tier.META
    if msg_type.startswith("-"):
        return Tier.MINOR
    return Tier.MAJOR


def _split_args(parts: list[str]) -> tuple[list[str], dict[str, str]]:
    """Partition raw args into positional + ``[tag] value`` kwargs.

    Kwargs are trailing ``[tag]``-prefixed args (``[from] item: Life Orb``,
    ``[of] p2a: X``, flag-only ``[still]``/``[miss]``). Positional args before
    the first kwarg are preserved verbatim (including meaningful blanks, e.g.
    a blank move target in ``|move|src|Protect||[still]``).
    """
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    in_kwargs = False
    for arg in parts:
        m = _KWARG_RE.match(arg)
        if m:
            in_kwargs = True
            kwargs[m.group(1).lower()] = m.group(2).strip()
        elif not in_kwargs:
            positional.append(arg)
        else:
            # a bare token after kwargs began (rare) — attach to last kwarg
            if kwargs:
                last = next(reversed(kwargs))
                kwargs[last] = f"{kwargs[last]}|{arg}".strip("|")
    return positional, kwargs


def parse_line(line: str, *, index: int = -1) -> ProtocolEvent:
    """Parse one protocol line into a typed :class:`ProtocolEvent`.

    Never raises on an unknown/malformed type — it degrades to a generic event
    tiered by the hyphen rule, so a renderer can always show *something* safe
    (digest §7: malformed event → safe placeholder, never crash).
    """
    # Showdown lines start with '|'. Splitting yields a leading '' element.
    # Bare '|' -> ['', ''] -> type ''. A line missing the leading pipe is
    # tolerated (treated as a raw type token).
    if line.startswith("|"):
        parts = line.split("|")[1:]
    else:
        parts = line.split("|")
    msg_type = parts[0] if parts else ""
    if msg_type in OPAQUE_PAYLOAD_TYPES and line.startswith("|"):
        # Keep `lead` structured fields, then ONE opaque tail that may carry pipes
        # (JSON/HTML/free text) — so `parse_request(ev.args[-1])` sees valid JSON
        # even when an opponent nickname contains `|`, while `|uhtml|NAME|HTML` /
        # `|c:|TIME|USER|MSG` keep their NAME/USER prefixes for attribution.
        lead = OPAQUE_PAYLOAD_TYPES[msg_type]
        prefix = f"|{msg_type}|"
        body = line[len(prefix) :] if line.startswith(prefix) else "|".join(parts[1:])
        if msg_type == "error" and body.split("|", 1)[0] not in ("p1", "p2"):
            # |error| is bare Showdown text by default. The sidecar augments CAPTURED
            # control errors with a side prefix (`|error|p1|msg`, lead 1), but a raw /
            # persisted bare `|error|TEXT` whose TEXT carries a pipe (e.g.
            # `[Unavailable choice] move|1 is disabled`) must stay ONE opaque arg —
            # only peel a side when the first field really is one. PR #223 review.
            lead = 0
        positional = body.split("|", lead) if lead else [body]
        kwargs: dict[str, str] = {}
    else:
        rest = parts[1:]
        positional, kwargs = _split_args(rest)
    idents = [PokemonIdent.parse(a) for a in positional if _IDENT_RE.match(a.strip())]
    # Kwarg values can ALSO carry an opponent-controlled ident — e.g.
    # `|-ability|...|[of] p2a: <nickname>` on cause lines. Left verbatim, a
    # renderer/agent prompt that shows `[of]` ownership would bypass the A6
    # nickname boundary. Extract a sanitized PokemonIdent AND rewrite the kwarg
    # value's nickname in place so every consumable surface is sanitized; only
    # `raw` stays verbatim for hashing (PR #200 review 3431806028).
    for key, val in kwargs.items():
        if _IDENT_RE.match(val.strip()):
            ident = PokemonIdent.parse(val)
            idents.append(ident)
            kwargs[key] = (
                f"{ident.side}{ident.position}: {ident.name}" if ident.side else ident.name
            )
    turn_no: int | None = None
    if msg_type == "turn" and positional:
        try:
            turn_no = int(positional[0])
        except ValueError:
            turn_no = None
    return ProtocolEvent(
        raw=line,
        type=msg_type,
        tier=tier_of(msg_type),
        args=tuple(positional),
        kwargs=kwargs,
        idents=tuple(idents),
        index=index,
        turn_no=turn_no,
    )


def parse_stream(lines: list[str]) -> list[ProtocolEvent]:
    """Parse an append-only line list into indexed events (pure function).

    Same input → identical output; assigns a monotonic :attr:`~ProtocolEvent.index`
    to every event so any renderer can scrub/seek by position and ``|turn|``
    anchors segment the timeline.
    """
    return [parse_line(line, index=i) for i, line in enumerate(lines)]


def is_section_break(ev: ProtocolEvent) -> bool:
    """True for the bare ``|`` divider (raw is exactly ``|``) or a ``|turn|`` — a
    renderer rule point.

    An EMPTY line (``raw == ""``) is NOT a section break even though it parses to
    the same empty divider *type*: a trailing newline in ``chunk.split("\\n")``
    yields ``""``, and treating that as a real divider would inject phantom
    separators into renders / replay / hash folds (PR #200 review 3431806048).
    """
    return ev.type == "turn" or ev.raw == "|"


def line_type(line: str) -> str:
    """The message type of a raw line, without fully parsing it.

    Cheap pre-filter for determinism stripping — avoids building a
    :class:`ProtocolEvent` per line just to read its type.
    """
    if line.startswith("|"):
        body = line[1:]
        bar = body.find("|")
        return body if bar == -1 else body[:bar]
    return line


def strip_nondeterministic(lines: list[str]) -> list[str]:
    """Drop lines whose type is in :data:`NONDETERMINISTIC_TYPES` (e.g. ``|t:|``).

    This is the canonicalization the ``(seed, inputLog)`` verify/hash path
    (digest §1, Phase 5) runs before comparing or hashing a protocol log: two
    re-simulations of the same battle differ ONLY in wall-clock ``|t:|`` lines,
    so the stripped logs MUST be byte-identical.
    """
    return [ln for ln in lines if line_type(ln) not in NONDETERMINISTIC_TYPES]


def project_frame(lines: list[str], *, side: str) -> list[str]:
    """Project an omniscient PS protocol delta to ONE viewer's perspective, per the
    live-viewer contract (``tasks/agentdex-builders-ga/LIVE_VIEWER_CONTRACT.md``).

    ``side`` is the owner's side (``"p1"`` / ``"p2"``) or ``"spectator"``.

    A ``|split|pX`` block is a **three-line sentinel**: the ``|split|pX`` marker, then
    pX's PRIVATE line (exact HP, e.g. ``176/298``), then its PUBLIC twin (percent HP,
    e.g. ``60/100``). For every block the marker is **DROPPED** (it is a control
    sentinel, never a renderable line — ``|split|`` itself is never shown) and exactly
    ONE data line is kept:

    - the owner of side ``pX`` keeps the PRIVATE line for its OWN block
      (``|split|pX`` where ``pX == side``) and the PUBLIC twin for the OPPONENT block;
    - a ``"spectator"`` keeps only the PUBLIC twin of every block.

    Non-split lines: ``|t:|`` wall-clock lines are stripped; a
    ``|player|SIDE|NAME|AVATAR|RATING`` line has its RATING **blanked** (delimiters
    preserved, so ``SIDE|NAME|AVATAR|RATING`` stays parseable) on any view that does not
    own that side — always for a spectator, the OPPONENT's ``|player|`` on an owner
    stream — so a ladder rating never leaks; and — **deny-by-default** — EVERY OTHER
    ``Tier.META`` ``"hidden"`` line is DROPPED for every side. That secret/control-meta
    set includes ``|request|`` (a side's FULL private team JSON — exact HP + movesets),
    ``|error|``, ``|seed|`` (PRNG echo → RNG re-derivation), ``|poke|`` /
    ``|teampreview|`` / ``|updatepoke|`` (team reveal), ``|badge|``, ``|rated|`` … AND any
    NEW hidden meta type added later, so the projector can never silently leak a future
    hidden channel (an allowlist of *redacted* types is unsound; this denies by default).
    Public battle EVENTS (``|move|`` / ``|-damage|`` / ``|switch|`` / ``|turn|`` /
    ``|faint|`` …) are ``Tier.MAJOR`` / ``Tier.MINOR``, and public reducer metadata like
    ``|teamsize|`` is META-but-not-hidden, so they pass through untouched. A bare
    ``|split|`` marker, the opponent's exact HP / team / rating, and the battle seed
    therefore never reach a viewer that should only see the public projection. (The owner
    sees their OWN exact HP via the kept ``|split|pX`` private line, not via
    ``|request|``.)
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        lt = line_type(ln)
        if lt in NONDETERMINISTIC_TYPES:  # |t:| wall clock — never emitted
            i += 1
            continue
        if lt == SPLIT_TYPE:
            # ``|split|pX`` then private(pX) then public — drop the marker, keep one.
            block_side = ln.split("|")[2] if ln.count("|") >= 2 else ""
            private_ln = lines[i + 1] if i + 1 < n else None
            public_ln = lines[i + 2] if i + 2 < n else None
            keep = private_ln if (side != "spectator" and block_side == side) else public_ln
            if keep is not None:
                out.append(keep)
            i += 3  # consume marker + private + public as one block
            continue
        if lt == "player":
            # |player|SIDE|NAME|AVATAR|RATING — blank RATING unless this is the
            # viewer's OWN side (a spectator owns no side, so it blanks every rating).
            parts = ln.split("|")
            player_side = parts[2] if len(parts) > 2 else ""
            if (side == "spectator" or player_side != side) and len(parts) >= 6:
                parts[5] = ""  # blank the rating value, keep the positional delimiters
                ln = "|".join(parts)
            out.append(ln)
            i += 1
            continue
        spec = MESSAGE_TYPES.get(lt)
        if spec is not None and spec.tier is Tier.META and spec.lane == "hidden":
            # DENY-BY-DEFAULT: every other META "hidden" line is control/secret meta,
            # never a renderable event — |request| (full team JSON), |error|, |seed|
            # (PRNG echo), |poke|/|teampreview|/|updatepoke| (team reveal), |badge|,
            # |rated|, … + any FUTURE hidden type. Dropped for every side so a new
            # hidden channel can't silently leak. Public battle EVENTS are Tier.MAJOR/
            # MINOR (never META-hidden), so they fall through to the append below.
            i += 1
            continue
        out.append(ln)
        i += 1
    return out


# ---------------------------------------------------------------------------
# UI-5: server-side scene snapshot
# ---------------------------------------------------------------------------


def _parse_hpstatus(hpstatus: str) -> tuple[float, str]:
    """Parse ``'cur/max [STATUS]'`` or ``'0 fnt'`` into ``(hpFrac, status)``."""
    parts = hpstatus.strip().split(None, 2)
    if not parts:
        return 1.0, ""
    hp_part = parts[0]
    status = parts[1] if len(parts) > 1 else ""
    if hp_part == "0" and status == "fnt":
        return 0.0, "fnt"
    if "/" in hp_part:
        try:
            cur_s, max_s = hp_part.split("/", 1)
            cur, mx = float(cur_s), float(max_s)
            return (cur / mx if mx > 0 else 0.0), status
        except ValueError:
            pass
    return 1.0, status


def scene_initial() -> dict:
    """Return a default scene state dict for incremental accumulation."""

    def mon() -> dict:
        return {
            "species": None,
            "hpFrac": None,
            "status": None,
            "name": None,
            "gender": None,
            "fainted": False,
        }

    return {
        "p1": mon(),
        "p2": mon(),
        "players": {"p1": None, "p2": None},
        "weather": None,
        "field": [],
        "teams": {"p1": {}, "p2": {}},
        "turn": 0,
        "winner": None,
    }


def _parse_details(details: str) -> tuple[str | None, str | None]:
    """Parse ``'Species, L50, M'`` details into ``(species, gender)``."""
    toks = [tok.strip() for tok in str(details or "").split(",")]
    species = toks[0] or None
    gender = next((tok for tok in toks[1:] if tok in ("M", "F")), None)
    return species, gender


def _field_entry(effect: str, side: str | None = None) -> dict:
    return {"effect": effect, "side": side}


def fold_scene(lines: list[str], state: dict) -> None:
    """Update mutable *state* in-place from PROJECTED protocol lines.

    Caller passes the same dict on every frame to get a running cumulative
    scene snapshot matching ``web/dashboard/vendor/live/scene.js``.
    """
    for raw_line in lines:
        lt = line_type(raw_line)
        if lt in NONDETERMINISTIC_TYPES:
            continue
        ev = parse_line(raw_line)

        if lt == "player":
            parts = raw_line.split("|")
            if len(parts) >= 4:
                player_side = parts[2]
                if player_side in ("p1", "p2"):
                    state["players"][player_side] = sanitize_name(parts[3])

        elif lt in ("switch", "drag", "replace", "detailschange"):
            if len(ev.args) >= 3:
                ident = ev.idents[0] if ev.idents else None
                species, gender = _parse_details(ev.args[1])
                hp_frac, status = _parse_hpstatus(ev.args[2])
                if ident and ident.side in ("p1", "p2"):
                    state[ident.side] = {
                        "species": species,
                        "gender": gender,
                        "name": ident.name or species,
                        "hpFrac": hp_frac,
                        "status": status or None,
                        "fainted": status == "fnt" or hp_frac <= 0,
                    }
                    if species:
                        state["teams"][ident.side].setdefault(species, {"fainted": False})

        elif lt in ("-damage", "-heal", "-sethp"):
            if len(ev.args) >= 2:
                ident = ev.idents[0] if ev.idents else None
                hp_frac, status = _parse_hpstatus(ev.args[1])
                if ident and ident.side in ("p1", "p2"):
                    s = state[ident.side]
                    if lt == "-heal" and s.get("name") and ident.name and ident.name != s["name"]:
                        continue
                    s["hpFrac"] = hp_frac
                    if status:
                        s["status"] = status
                    if status == "fnt" or hp_frac <= 0:
                        s["fainted"] = True
                        if s.get("species"):
                            state["teams"][ident.side].setdefault(s["species"], {})["fainted"] = (
                                True
                            )

        elif lt == "faint":
            ident = ev.idents[0] if ev.idents else None
            if ident and ident.side in ("p1", "p2"):
                state[ident.side]["hpFrac"] = 0.0
                state[ident.side]["status"] = "fnt"
                state[ident.side]["fainted"] = True
                species = state[ident.side].get("species")
                if species:
                    state["teams"][ident.side].setdefault(species, {})["fainted"] = True

        elif lt == "-status":
            if len(ev.args) >= 2:
                ident = ev.idents[0] if ev.idents else None
                if ident and ident.side in ("p1", "p2"):
                    state[ident.side]["status"] = ev.args[1]

        elif lt == "-curestatus":
            ident = ev.idents[0] if ev.idents else None
            if ident and ident.side in ("p1", "p2"):
                state[ident.side]["status"] = None

        elif lt == "-weather":
            if ev.args:
                w = ev.args[0]
                state["weather"] = None if w.lower() == "none" else w

        elif lt == "-fieldstart":
            if ev.args:
                entry = _field_entry(ev.args[0])
                if entry not in state["field"]:
                    state["field"].append(entry)

        elif lt == "-fieldend":
            if ev.args:
                state["field"] = [
                    entry for entry in state["field"] if entry["effect"] != ev.args[0]
                ]

        elif lt == "-sidestart":
            if len(ev.args) >= 2:
                entry = _field_entry(ev.args[1], ev.args[0])
                if entry not in state["field"]:
                    state["field"].append(entry)

        elif lt == "-sideend":
            if len(ev.args) >= 2:
                state["field"] = [
                    entry
                    for entry in state["field"]
                    if not (entry["effect"] == ev.args[1] and entry["side"] == ev.args[0])
                ]

        elif lt == "turn":
            turn_no = getattr(ev, "turn_no", getattr(ev, "turnNo", None))
            if turn_no is not None:
                state["turn"] = turn_no

        elif lt == "win":
            if ev.args:
                state["winner"] = sanitize_name(ev.args[0])


# ---------------------------------------------------------------------------
# UI-6: per-move reasoning trace extraction
# ---------------------------------------------------------------------------


def extract_trace_lines(lines: list[str]) -> list[dict]:
    """Extract reasoning/say entries from PROJECTED protocol lines.

    Returns ``[{side, text}, ...]`` for every ``|-reasoning|SIDE|TEXT`` and
    ``|say|SIDE|TEXT`` line.  Attach as ``trace_lines`` in the SSE payload so
    the Agent Pane can render per-move rationale.
    """
    out: list[dict] = []
    for raw_line in lines:
        lt = line_type(raw_line)
        if lt not in (REASONING_TYPE, SAY_TYPE):
            continue
        ev = parse_line(raw_line)
        if len(ev.args) >= 2:
            out.append({"side": ev.args[0], "text": ev.args[1]})
        elif len(ev.args) == 1:
            out.append({"side": "", "text": ev.args[0]})
    return out
