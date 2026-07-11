"""Bounded poke-env ladder windows with battle-backed rating evidence."""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlsplit


@dataclass(frozen=True)
class LadderWindow:
    rating: float
    battle_tag: str
    opponents: tuple[str, ...]
    wall_clock_sec: float


@dataclass(frozen=True)
class LeaderboardRating:
    skill_rating: float
    ref: str


class _LadderTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _showdown_id(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _parse_skill_rating(document: str, username: str) -> float:
    parser = _LadderTableParser()
    parser.feed(document)
    header = next((row for row in parser.rows if "Agent" in row and "Skill Rating" in row), None)
    if header is None:
        raise RuntimeError("PokeAgent leaderboard omitted Agent/Skill Rating columns")
    agent_col, rating_col = header.index("Agent"), header.index("Skill Rating")
    target = _showdown_id(username)
    row = next(
        (
            row
            for row in parser.rows
            if len(row) > max(agent_col, rating_col) and _showdown_id(row[agent_col]) == target
        ),
        None,
    )
    if row is None:
        raise RuntimeError(f"agent {username!r} is not present on the PokeAgent leaderboard")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", row[rating_col])
    if match is None:
        raise RuntimeError(f"agent {username!r} has no FH-BT skill rating")
    return float(match.group())


async def query_skill_rating(
    websocket_url: str, *, battle_format: str, username: str, timeout_sec: float
) -> LeaderboardRating:
    """Query the public ``laddertop`` response and read primary FH-BT quality."""
    import websockets

    async with asyncio.timeout(timeout_sec):
        async with websockets.connect(websocket_url, open_timeout=timeout_sec) as socket:
            await socket.recv()
            await socket.send(f"|/cmd laddertop {battle_format}")
            while True:
                message = str(await socket.recv())
                if not message.startswith("|queryresponse|laddertop|"):
                    continue
                payload = json.loads(message.split("|", 3)[3])
                if not isinstance(payload, list) or len(payload) != 2:
                    raise RuntimeError("invalid PokeAgent laddertop response")
                rating = _parse_skill_rating(str(payload[1]), username)
                host = urlsplit(websocket_url).netloc
                ref = f"https://{host}/ladder#{quote(battle_format)}/{quote(username)}"
                return LeaderboardRating(rating, ref)


async def run_ladder_window(player: Any, *, n_games: int, timeout_sec: float) -> LadderWindow:
    """Play rated games, enforce the budget, and always close the PS socket."""
    if n_games <= 0 or timeout_sec <= 0:
        raise ValueError("n_games and timeout_sec must both be > 0")
    started = time.monotonic()
    try:
        await asyncio.wait_for(player.ladder(n_games), timeout=timeout_sec)
        completed = [battle for battle in player.battles.values() if battle.finished]
        rated = [battle for battle in completed if battle.rating is not None]
        if not rated:
            raise RuntimeError("ladder window completed without a server rating")
        latest = rated[-1]
        return LadderWindow(
            rating=float(latest.rating),
            battle_tag=str(latest.battle_tag),
            opponents=tuple(str(b.opponent_username or "") for b in completed),
            wall_clock_sec=max(time.monotonic() - started, 0.0),
        )
    finally:
        try:
            await player.ps_client.stop_listening()
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass
