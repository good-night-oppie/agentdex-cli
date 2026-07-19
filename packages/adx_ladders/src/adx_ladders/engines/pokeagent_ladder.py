"""Real PokeAgent ladder engine over an out-of-process candidate policy."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from adx_frontier.candidate import AgentCandidate
from adx_showdown.selfplay.entrypoint_agent import EntrypointAgent
from adx_showdown.selfplay.ladder import (
    LadderWindow,
    LeaderboardRating,
    query_skill_rating,
    run_ladder_window,
)

from adx_ladders.adapters.pokeagent import PokeAgentResult


def _showdown_id(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


class PokeAgentLadderRunner:
    def __init__(
        self,
        *,
        username: str,
        password: str,
        websocket_url: str,
        authentication_url: str,
        team: str,
        baseline_opponents: Iterable[str],
        n_games: int = 1,
        battle_format: str = "gen1ou",
        move_timeout_sec: float = 30.0,
        cost_dollar: float | None = None,
        player_factory: Callable[[AgentCandidate, EntrypointAgent], Any] | None = None,
        window_runner: Callable[..., Awaitable[LadderWindow]] = run_ladder_window,
        leaderboard_reader: Callable[..., Awaitable[LeaderboardRating]] = query_skill_rating,
    ) -> None:
        self.username, self.password = username, password
        self.websocket_url, self.authentication_url = websocket_url, authentication_url
        self.team = team
        self.baselines = frozenset(_showdown_id(name) for name in baseline_opponents)
        self.n_games, self.battle_format = n_games, battle_format
        self.move_timeout_sec, self.cost_dollar = move_timeout_sec, cost_dollar
        self.player_factory, self.window_runner = player_factory, window_runner
        self.leaderboard_reader = leaderboard_reader

    def __call__(self, candidate: AgentCandidate, timeout_sec: float) -> PokeAgentResult:
        return asyncio.run(self._run(candidate, timeout_sec))

    async def _run(self, candidate: AgentCandidate, timeout_sec: float) -> PokeAgentResult:
        started = time.monotonic()
        with EntrypointAgent(
            candidate.entrypoint, cwd=candidate.root, timeout_sec=self.move_timeout_sec
        ) as decide:
            player = (
                self.player_factory(candidate, decide)
                if self.player_factory is not None
                else self._make_player(candidate, decide)
            )
            window = await self.window_runner(player, n_games=self.n_games, timeout_sec=timeout_sec)
        remaining = timeout_sec - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("PokeAgent budget expired before FH-BT leaderboard read")
        leaderboard = await self.leaderboard_reader(
            self.websocket_url,
            battle_format=self.battle_format,
            username=self.username,
            timeout_sec=remaining,
        )
        opponents = tuple(_showdown_id(name) for name in window.opponents)
        community = sum(bool(name) and name not in self.baselines for name in opponents)
        measured = self.cost_dollar is not None
        return PokeAgentResult(
            rating=leaderboard.skill_rating,
            rating_ref=leaderboard.ref,
            community_opponents=community,
            total_opponents=len(opponents),
            wall_clock_sec=max(time.monotonic() - started, 0.0),
            cost_dollar=self.cost_dollar if measured else candidate.budget.usd,
            cost_is_measured=measured,
        )

    def _make_player(self, candidate: AgentCandidate, decide: EntrypointAgent) -> Any:
        from adx_showdown.harness import BattleHarness
        from adx_showdown.selfplay.runner import make_harness_player
        from poke_env import AccountConfiguration, ServerConfiguration

        return make_harness_player(
            BattleHarness(harness_id=candidate.name, move_selection_strategy="llm_freeform"),
            account=AccountConfiguration(self.username, self.password),
            server=ServerConfiguration(self.websocket_url, self.authentication_url),
            battle_format=self.battle_format,
            decide=decide,
            team=self.team,
        )
