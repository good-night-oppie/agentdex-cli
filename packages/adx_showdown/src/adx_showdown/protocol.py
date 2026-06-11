"""Showdown protocol parsing + the A6 sanitizer boundary.

IDEAL_EXPERIENCE §Arena A6: every opponent-controlled string is sanitized AT
THE PROTOCOL-PARSE BOUNDARY before it can reach any agent or LLM context.
One chokepoint (:func:`sanitize_name`) closes both judge-injection and
cross-visitor injection lanes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Allowlist per ADR-0010 §Measured-constraints: [A-Za-z0-9 _-] only.
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9 _-]+")
_WS_RE = re.compile(r"\s+")
MAX_NAME_LEN = 24


def sanitize_name(raw: object, *, max_len: int = MAX_NAME_LEN) -> str:
    """Strip everything outside the allowlist; collapse whitespace; bound length.

    Applied to player names, nicknames, team names — any string an opponent
    or visitor controls — the moment it is parsed out of the protocol.
    """
    text = str(raw) if raw is not None else ""
    text = _SAFE_CHARS_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_len]


class ActiveMove(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)
    slot: int
    id: str = ""
    move: str = ""
    disabled: bool = False
    pp: int = 0
    maxpp: int = 0


class BenchSlot(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)
    index: int  # 1-based for choice strings
    name: str = ""  # SANITIZED nickname
    species: str = ""
    condition: str = ""
    active: bool = False

    @property
    def fainted(self) -> bool:
        return self.condition.endswith(" fnt") or self.condition == "0 fnt"


class ParsedRequest(BaseModel):
    """A |request| sideupdate, parsed + sanitized."""

    model_config = ConfigDict(extra="ignore", strict=False)
    side_id: str = ""
    wait: bool = False
    team_preview: bool = False
    force_switch: list[bool] = Field(default_factory=list)
    active_moves: list[list[ActiveMove]] = Field(default_factory=list)
    trapped: bool = False  # active slot 0 cannot switch (revealed pre-choice)
    bench: list[BenchSlot] = Field(default_factory=list)
    rqid: int | None = None


def parse_request(request: dict[str, Any] | str) -> ParsedRequest:
    """Parse a raw |request| JSON into the sanitized :class:`ParsedRequest`."""
    data: dict[str, Any] = json.loads(request) if isinstance(request, str) else request
    side = data.get("side") or {}
    bench: list[BenchSlot] = []
    for idx, poke in enumerate(side.get("pokemon") or [], start=1):
        ident = str(poke.get("ident", ""))
        nickname = ident.split(":", 1)[1].strip() if ":" in ident else ident
        details = str(poke.get("details", ""))
        species = details.split(",", 1)[0]
        bench.append(
            BenchSlot(
                index=idx,
                name=sanitize_name(nickname),
                species=sanitize_name(species),
                condition=str(poke.get("condition", "")),
                active=bool(poke.get("active", False)),
            )
        )
    active_moves: list[list[ActiveMove]] = []
    trapped = False
    for slot_data in data.get("active") or []:
        if slot_data and bool(slot_data.get("trapped", False)):
            trapped = True
        moves: list[ActiveMove] = []
        for mi, mv in enumerate((slot_data or {}).get("moves") or [], start=1):
            moves.append(
                ActiveMove(
                    slot=mi,
                    id=str(mv.get("id", "")),
                    move=sanitize_name(mv.get("move", ""), max_len=32),
                    disabled=bool(mv.get("disabled", False)),
                    pp=int(mv.get("pp", 0) or 0),
                    maxpp=int(mv.get("maxpp", 0) or 0),
                )
            )
        active_moves.append(moves)
    return ParsedRequest(
        side_id=str(side.get("id", "")),
        wait=bool(data.get("wait", False)),
        team_preview=bool(data.get("teamPreview", False)),
        force_switch=[bool(x) for x in (data.get("forceSwitch") or [])],
        active_moves=active_moves,
        trapped=trapped,
        bench=bench,
        rqid=data.get("rqid"),
    )


def legal_choices(req: ParsedRequest) -> list[str]:
    """Enumerate legal choice strings for a parsed request (singles only)."""
    if req.wait:
        return []
    if req.team_preview:
        return [f"team {i}" for i in range(1, len(req.bench) + 1)]
    choices: list[str] = []
    if req.force_switch and any(req.force_switch):
        for slot in req.bench:
            if not slot.active and not slot.fainted:
                choices.append(f"switch {slot.index}")
        return choices
    for moves in req.active_moves[:1]:
        for mv in moves:
            if not mv.disabled:
                choices.append(f"move {mv.slot}")
    if not req.trapped:
        for slot in req.bench:
            if not slot.active and not slot.fainted:
                choices.append(f"switch {slot.index}")
    return choices


def move_only_choices(req: ParsedRequest) -> list[str]:
    """Fallback set when a switch was rejected (maybeTrapped revealed late)."""
    return [c for c in legal_choices(req) if c.startswith("move")]


def switch_only_choices(req: ParsedRequest) -> list[str]:
    """Fallback set when a move was rejected (e.g. Disable/Imprison race)."""
    return [
        f"switch {slot.index}"
        for slot in req.bench
        if not slot.active and not slot.fainted
    ]
