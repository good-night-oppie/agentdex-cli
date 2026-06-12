"""Arena ladder — Glicko-2 over rating periods (= evolution generations).

IDEAL §Arena anchors enforced in code, not prose:
- A2: a rating event WITHOUT a re-simulable inputLog hash is rejected.
- A4: `published_delta` returns None (INCONCLUSIVE) when |delta| < 2·RD.
- Frozen anchors are pinned — their ratings never move; they are the
  instrument's reference marks (calibration orders them nightly).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from agentdex_engine.modules.arena.glicko import Rating, update_rating

_HASH_RE = re.compile(r"^[0-9a-f]{32}$")


class RatingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    battle_id: str = Field(min_length=1)
    p1: str = Field(min_length=1)
    p2: str = Field(min_length=1)
    winner: str  # "" == tie
    input_log_blake2b16: str  # REQUIRED (A2) — validated in Ladder.rate_period


class InvalidRatingEvent(ValueError):
    """Event lacked the A2 re-simulable inputLog hash (or named no entrant)."""


class Ladder:
    def __init__(self) -> None:
        self._ratings: dict[str, Rating] = {}
        self._frozen: set[str] = set()

    def register(self, name: str, *, frozen: bool = False, rating: Rating | None = None) -> None:
        if name not in self._ratings:
            self._ratings[name] = rating or Rating()
        if frozen:
            self._frozen.add(name)

    def rating(self, name: str) -> Rating:
        return self._ratings[name]

    @property
    def entrants(self) -> dict[str, Rating]:
        return dict(self._ratings)

    def rate_period(self, events: list[RatingEvent]) -> dict[str, Rating]:
        """Apply one rating period. All opponent ratings are PRE-period
        snapshots (Glicko-2 spec). Returns the post-period ratings."""
        pre = {k: v.model_copy() for k, v in self._ratings.items()}
        per_player: dict[str, list[tuple[Rating, float]]] = {k: [] for k in pre}
        for ev in events:
            if not _HASH_RE.match(ev.input_log_blake2b16 or ""):
                raise InvalidRatingEvent(
                    f"{ev.battle_id}: rating event rejected — no re-simulable inputLog hash (A2)"
                )
            for name in (ev.p1, ev.p2):
                if name not in pre:
                    raise InvalidRatingEvent(f"{ev.battle_id}: unknown entrant {name!r}")
            s1 = 0.5 if ev.winner == "" else (1.0 if ev.winner == ev.p1 else 0.0)
            per_player[ev.p1].append((pre[ev.p2], s1))
            per_player[ev.p2].append((pre[ev.p1], 1.0 - s1))
        for name, results in per_player.items():
            if name in self._frozen:
                continue
            self._ratings[name] = update_rating(pre[name], results)
        return dict(self._ratings)

    @staticmethod
    def published_delta(before: Rating, after: Rating) -> float | None:
        """A4 rail: the ONE number the arena sells — or None (INCONCLUSIVE)
        when the move is smaller than twice the post-period deviation."""
        delta = after.rating - before.rating
        return delta if abs(delta) >= 2.0 * after.rd else None

    @staticmethod
    def intervals_overlap(a: Rating, b: Rating) -> bool:
        """2·RD interval overlap — calibration's anchor-separation check."""
        return abs(a.rating - b.rating) < 2.0 * a.rd + 2.0 * b.rd
