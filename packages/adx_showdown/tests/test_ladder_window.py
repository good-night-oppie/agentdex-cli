from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from adx_showdown.selfplay.ladder import _parse_skill_rating, run_ladder_window


class _Player:
    def __init__(self, battles: dict, *, block: bool = False) -> None:
        self.battles = battles
        self.block = block
        self.stopped = False
        self.ps_client = SimpleNamespace(stop_listening=self._stop)

    async def ladder(self, n_games: int) -> None:
        assert n_games == 2
        if self.block:
            await asyncio.sleep(10)

    async def _stop(self) -> None:
        self.stopped = True


def test_ladder_window_returns_latest_server_rating_and_opponents() -> None:
    battles = {
        "one": SimpleNamespace(
            finished=True, rating=1490, battle_tag="gen1ou-1", opponent_username="baseline-a"
        ),
        "two": SimpleNamespace(
            finished=True, rating=1512, battle_tag="gen1ou-2", opponent_username="community-b"
        ),
    }
    player = _Player(battles)
    result = asyncio.run(run_ladder_window(player, n_games=2, timeout_sec=1))
    assert (result.rating, result.battle_tag) == (1512.0, "gen1ou-2")
    assert result.opponents == ("baseline-a", "community-b")
    assert result.wall_clock_sec >= 0 and player.stopped


def test_ladder_window_times_out_and_closes_socket() -> None:
    player = _Player({}, block=True)
    with pytest.raises(TimeoutError):
        asyncio.run(run_ladder_window(player, n_games=2, timeout_sec=0.01))
    assert player.stopped


def test_ladder_window_rejects_missing_rating_and_closes_socket() -> None:
    player = _Player({"one": SimpleNamespace(finished=True, rating=None)})
    with pytest.raises(RuntimeError, match="without a server rating"):
        asyncio.run(run_ladder_window(player, n_games=2, timeout_sec=1))
    assert player.stopped


def test_parse_primary_fhbt_skill_rating_from_public_table() -> None:
    document = """
    <table><tr><th>#</th><th>Agent</th><th>Team</th><th>Skill Rating</th><th>ELO</th></tr>
    <tr><td>1</td><td>Other</td><td>T</td><td>1809 ±7</td><td>2264</td></tr>
    <tr><td>2</td><td>adx-bot-1</td><td>AgentDex</td><td>1512 ±20</td><td>1600</td></tr></table>
    """
    assert _parse_skill_rating(document, "ADX Bot 1") == 1512.0


def test_parse_fhbt_rejects_agent_absent_from_leaderboard() -> None:
    document = "<table><tr><th>Agent</th><th>Skill Rating</th></tr></table>"
    with pytest.raises(RuntimeError, match="not present"):
        _parse_skill_rating(document, "adx-bot-1")
