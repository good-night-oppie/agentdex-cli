from __future__ import annotations

import sys

from adx_frontier.candidate import AgentCandidate, Budget
from adx_ladders.engines.pokeagent_ladder import PokeAgentLadderRunner
from adx_showdown.selfplay.ladder import LadderWindow, LeaderboardRating


def test_runner_drives_candidate_and_classifies_opponent_window(tmp_path) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " msg=json.loads(line)\n"
        " print(json.dumps({'type':'action','action':'tackle'}),flush=True)\n"
    )
    candidate = AgentCandidate(
        "agent",
        f"{sys.executable} agent.py",
        ("agent.py",),
        "model",
        Budget(2.5, 1),
        ("pokeagent-gen1ou",),
        tmp_path,
    )
    seen = {}

    def player_factory(got_candidate, decide):
        seen["candidate"] = got_candidate
        seen["action"] = decide(None, {"available_moves": [{"id": "tackle"}]})
        return object()

    async def window_runner(player, *, n_games, timeout_sec):
        seen["window"] = (player, n_games, timeout_sec)
        return LadderWindow(1512, "gen1ou-42", ("Baseline A", "Community-X", ""), 9.0)

    async def leaderboard_reader(url, *, battle_format, username, timeout_sec):
        seen["leaderboard"] = (url, battle_format, username, timeout_sec)
        return LeaderboardRating(1701, "https://ratings.example/leaderboard#agent")

    runner = PokeAgentLadderRunner(
        username="adx-bot-1",
        password="test-only",  # pragma: allowlist secret
        websocket_url="wss://ps.example/ws",
        authentication_url="https://ps.example/auth",
        team="TEAM",
        baseline_opponents=["baseline-a"],
        n_games=3,
        player_factory=player_factory,
        window_runner=window_runner,
        leaderboard_reader=leaderboard_reader,
    )
    result = runner(candidate, 60.0)
    assert seen["candidate"] is candidate and seen["action"] == "tackle"
    assert seen["window"][1:] == (3, 60.0)
    assert (result.community_opponents, result.total_opponents) == (1, 3)
    assert result.rating == 1701 and result.rating_ref.endswith("#agent")
    assert result.cost_dollar == 2.5 and not result.cost_is_measured
