"""adx-client — the state reducer: fold the typed protocol stream into one
queryable :class:`BattleState` (digest §2 / P1-b, the @pkmn ``@pkmn/client`` layer).

The renderer paints from THIS folded state and nothing else. There is exactly
one source of truth — the ordered event stream — so the HUD can never desync
from a side cache (digest §7: "don't recompute HUD state from memory; two
sources of truth desync"). Every field below is a pure function of the events
applied so far.

This module imports only :mod:`adx_showdown.lineproto` (types). It must never
reach "up" into the engine (``sidecar``/``sim``) or the view — a guard test
(``test_layering.py``) enforces that import direction.

``|split|`` note: the omniscient log carries each HP event twice — a private
(full-HP) line then a public (percentage) line (see the line-protocol doc). The
reducer applies both; the public line lands last and is the canonical display
percentage, so the folded ``hp_pct`` matches what a spectator sees. Perspective-
aware split resolution (omniscient vs spectator vs per-agent) is Phase 8.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.lineproto import ProtocolEvent, parse_stream
from adx_showdown.protocol import sanitize_name

_SIDES = ("p1", "p2")


def hp_pct_of(hpstatus: str) -> int:
    """Parse a protocol HP token (``cur/max [status]`` or ``0 fnt``) → percent.

    Rounds a PARTIAL HP up (Showdown's convention: 1 HP shows as 1%, never 0%),
    so a private line ``176/298`` → 60 matches the public ``60/100`` line — a
    perspective stream that keeps only the private line still agrees with the
    omniscient public value. ``round(...,6)`` first absorbs binary-float error
    (``55/100*100`` is ``55.00000000000001``; a bare ``ceil`` would overshoot to
    56). ``0 fnt`` / ``0`` → 0.
    """
    token = hpstatus.strip()
    if "fnt" in token:
        return 0
    hp = token.split(" ", 1)[0]
    if "/" in hp:
        cur, _, mx = hp.partition("/")
        try:
            c, m = int(cur), int(mx)
        except ValueError:
            return 100
        return math.ceil(round(c / m * 100, 6)) if m else 0
    try:
        return max(0, min(100, int(hp)))
    except ValueError:
        return 100


def status_of(hpstatus: str) -> str:
    """The status suffix carried in an HP token (``264/291 par`` → ``par``).

    A statused Pokémon switching back in re-states its condition here instead of
    re-emitting ``|-status|``, so the reducer reads it on switch / forme-change.
    ``fnt`` is fainting, not a status condition → ``""``.
    """
    parts = hpstatus.strip().split(" ", 1)
    if len(parts) > 1 and parts[1].strip() and parts[1].strip() != "fnt":
        return sanitize_name(parts[1].strip(), max_len=8)
    return ""


class SideState(BaseModel):
    """Folded state for one side of the battle (all derived from the stream)."""

    model_config = ConfigDict(extra="forbid")
    player_name: str = ""
    team_size: int = 0
    active_species: str = ""
    active_nickname: str = ""
    hp_pct: int = 100
    status: str = ""  # par / brn / slp / psn / tox / frz, or "" when healthy
    fainted_count: int = 0
    boosts: dict[str, int] = Field(default_factory=dict)  # stat → stage (-6..+6)

    @property
    def remaining_pips(self) -> int:
        """Roster pips still standing (for the pokeball-strip indicator)."""
        return max(0, self.team_size - self.fainted_count)


class BattleState(BaseModel):
    """The single folded battle state every renderer paints from."""

    model_config = ConfigDict(extra="forbid")
    turn_no: int = 0
    p1: SideState = Field(default_factory=SideState)
    p2: SideState = Field(default_factory=SideState)
    winner: str | None = None  # None = in progress; "" = tie; else the winner name
    ended: bool = False
    field: dict[str, str] = Field(default_factory=dict)  # weather / terrain
    # turn → {side: rationale}; populated from the agentdex `|-reasoning|` minor
    reasoning_by_turn: dict[int, dict[str, str]] = Field(default_factory=dict)

    def side(self, sid: str) -> SideState:
        return self.p1 if sid == "p1" else self.p2


class BattleClient:
    """Incrementally folds events one at a time; ``state`` is always current."""

    def __init__(self) -> None:
        self.state = BattleState()

    def apply(self, ev: ProtocolEvent) -> None:
        handler = getattr(self, f"_on_{_handler_name(ev.type)}", None)
        if handler is not None:
            handler(ev)

    # --- side helpers -------------------------------------------------------
    def _side_of(self, ev: ProtocolEvent) -> SideState | None:
        for ident in ev.idents:
            if ident.side in _SIDES:
                return self.state.side(ident.side)
        return None

    # --- majors -------------------------------------------------------------
    def _on_turn(self, ev: ProtocolEvent) -> None:
        if ev.turn_no is not None:
            self.state.turn_no = ev.turn_no

    def _on_player(self, ev: ProtocolEvent) -> None:
        # |player|p1|Alpha||
        if len(ev.args) >= 2 and ev.args[0] in _SIDES:
            self.state.side(ev.args[0]).player_name = sanitize_name(ev.args[1])

    def _on_teamsize(self, ev: ProtocolEvent) -> None:
        # |teamsize|p1|6
        if len(ev.args) >= 2 and ev.args[0] in _SIDES:
            try:
                self.state.side(ev.args[0]).team_size = int(ev.args[1])
            except ValueError:
                pass

    def _on_switch(self, ev: ProtocolEvent) -> None:
        # |switch|p1a: Nick|Species, L82, M|298/298 — a fresh mon: BOOSTS reset
        # (volatile), but STATUS persists and is re-stated in the HPSTATUS suffix
        # (Showdown emits no fresh |-status| for the switch-in). PR #208 review.
        side = self._side_of(ev)
        if side is None:
            return
        side.active_nickname = ev.idents[0].name
        if len(ev.args) >= 2:
            side.active_species = sanitize_name(ev.args[1].split(",", 1)[0], max_len=32)
        side.hp_pct = hp_pct_of(ev.args[2]) if len(ev.args) >= 3 else 100
        side.status = status_of(ev.args[2]) if len(ev.args) >= 3 else ""
        side.boosts = {}

    _on_drag = _on_switch  # forced switch — same shape + volatile reset
    _on_replace = _on_switch  # illusion (Zoroark) ended → the revealed true mon

    def _on_formechange(self, ev: ProtocolEvent) -> None:
        # |-formechange|POKEMON|SPECIES|HPSTATUS (temporary) / |detailschange| (permanent)
        # — the SAME active mon changes species and may carry an updated HP +
        # status suffix, so fold all three (volatiles persist — not a switch-in).
        # PR #200 review 3431806055 / PR #212 review.
        side = self._side_of(ev)
        if side is None:
            return
        if len(ev.args) >= 2:
            side.active_species = sanitize_name(ev.args[1].split(",", 1)[0], max_len=32)
        if len(ev.args) >= 3:
            hp_token = ev.args[2]
            if "/" in hp_token or "fnt" in hp_token:  # a real HPSTATUS, not a flag
                side.hp_pct = hp_pct_of(hp_token)
                side.status = status_of(hp_token)

    _on_detailschange = _on_formechange  # permanent forme — same species+HP update

    def _on_faint(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is not None:
            side.hp_pct = 0
            side.fainted_count += 1

    def _on_win(self, ev: ProtocolEvent) -> None:
        self.state.winner = sanitize_name(ev.args[0]) if ev.args else ""
        self.state.ended = True

    def _on_tie(self, ev: ProtocolEvent) -> None:
        self.state.winner = ""
        self.state.ended = True

    # --- minors (consequences) ---------------------------------------------
    def _on_damage(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is not None and len(ev.args) >= 2:
            side.hp_pct = hp_pct_of(ev.args[1])

    _on_heal = _on_damage
    _on_sethp = _on_damage

    def _on_status(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is not None and len(ev.args) >= 2:
            side.status = sanitize_name(ev.args[1], max_len=8)

    def _on_curestatus(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is not None:
            side.status = ""

    def _boost(self, ev: ProtocolEvent, sign: int) -> None:
        side = self._side_of(ev)
        if side is None or len(ev.args) < 3:
            return
        stat = sanitize_name(ev.args[1], max_len=4)
        try:
            amount = int(ev.args[2])
        except ValueError:
            return
        side.boosts[stat] = max(-6, min(6, side.boosts.get(stat, 0) + sign * amount))

    def _on_boost(self, ev: ProtocolEvent) -> None:
        self._boost(ev, +1)

    def _on_unboost(self, ev: ProtocolEvent) -> None:
        self._boost(ev, -1)

    def _on_setboost(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is None or len(ev.args) < 3:
            return
        try:
            side.boosts[sanitize_name(ev.args[1], max_len=4)] = int(ev.args[2])
        except ValueError:
            pass

    def _on_clearboost(self, ev: ProtocolEvent) -> None:
        side = self._side_of(ev)
        if side is not None:
            side.boosts = {}

    def _on_clearallboost(self, _ev: ProtocolEvent) -> None:
        # |-clearallboost| (Haze) clears BOTH sides' stat stages — no ident, so
        # the per-side _side_of() does not apply. PR #208 review.
        self.state.p1.boosts = {}
        self.state.p2.boosts = {}

    def _on_weather(self, ev: ProtocolEvent) -> None:
        if ev.args:
            self.state.field["weather"] = sanitize_name(ev.args[0], max_len=16)

    @staticmethod
    def _field_key(effect: str) -> str:
        # |-fieldstart|move: Grassy Terrain → "Grassy Terrain"
        return sanitize_name(effect.split(":", 1)[-1].strip(), max_len=24)

    def _on_fieldstart(self, ev: ProtocolEvent) -> None:
        # terrain / pseudo-weather (Trick Room, Grassy Terrain, …). BattleState.field
        # is documented to cover terrain, not just weather. PR #208 review.
        if ev.args:
            self.state.field[self._field_key(ev.args[0])] = "active"

    def _on_fieldend(self, ev: ProtocolEvent) -> None:
        if ev.args:
            self.state.field.pop(self._field_key(ev.args[0]), None)

    def _on_reasoning(self, ev: ProtocolEvent) -> None:
        # |-reasoning|<side>|<text> — agentdex's added rationale minor (P1-d)
        if len(ev.args) >= 2 and ev.args[0] in _SIDES:
            turn = self.state.turn_no
            self.state.reasoning_by_turn.setdefault(turn, {})[ev.args[0]] = ev.args[1]


def _handler_name(msg_type: str) -> str:
    """Map a protocol type to a handler suffix (``-damage`` → ``damage``)."""
    return msg_type.lstrip("-").replace(":", "")


def reduce(events: list[ProtocolEvent]) -> BattleState:
    """Fold an event list into the final :class:`BattleState` (pure function)."""
    client = BattleClient()
    for ev in events:
        client.apply(ev)
    return client.state


def reduce_lines(lines: list[str]) -> BattleState:
    """Convenience: parse raw protocol lines then fold them."""
    return reduce(parse_stream(lines))
