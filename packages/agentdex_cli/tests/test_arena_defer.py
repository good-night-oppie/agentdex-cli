"""test_arena_defer — the deferred `adx arena` stub.

The arena surface (enroll / battle / evolution) is intentionally NOT wired into
the adx CLI; it is driven through the starter kit or the MCP endpoint. The stub
exists so a visiting agent typing `adx arena ...` gets actionable routing
instead of a bare argparse "invalid choice" error (ADX-P2-001 agent-ux footgun).

Tests:
1. `adx arena` parses to cmd_arena_defer (the subcommand exists at all).
2. Running it fails closed (rc=1) and prints starter-kit + MCP routing to stderr.
3. Arbitrary trailing args (`adx arena evolve --foo`) are swallowed by REMAINDER
   and still route cleanly — no argparse error on unknown sub-subcommands.
4. `adx arena play ...` is the ONE wired verb — it routes to the terminal client
   (cmd_arena_play), NOT the defer stub.
"""

from __future__ import annotations

import pytest
from agentdex_cli.cli import build_parser, cmd_arena_defer, main


def test_arena_subcommand_exists_and_routes():
    parser = build_parser()
    args = parser.parse_args(["arena"])
    assert args.cmd == "arena"
    assert args.func is cmd_arena_defer


def test_arena_defer_fails_closed_with_routing(capsys):
    rc = main(["arena"])
    assert rc == 1  # the requested arena action did not run (not a usage error)
    err = capsys.readouterr().err
    # Routes the agent to the two real arena on-ramps + the protocol doc.
    assert "agent-starter-kit" in err
    assert "/mcp/" in err
    assert "skill.md" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["arena", "enroll", "--owner", "x@y.com"],
        ["arena", "battle", "--gym-leader", "gym-balance"],
        ["arena", "evolve", "--foo"],
    ],
)
def test_arena_swallows_trailing_args(argv, capsys):
    # REMAINDER must absorb any sub-args so the visiting agent never hits a
    # bare argparse "invalid choice" / "unrecognized arguments" error. (`play`
    # is excluded — it is the one implemented verb; see test below.)
    rc = main(argv)
    assert rc == 1
    assert "agent-starter-kit" in capsys.readouterr().err


def test_arena_play_routes_to_play_not_defer(monkeypatch, capsys):
    # `adx arena play ...` is wired to the terminal client, NOT the defer stub.
    called: dict[str, list[str]] = {}

    def fake_play(argv: list[str]) -> int:
        called["argv"] = argv
        return 0

    monkeypatch.setattr("agentdex_cli.arena_tui.cmd_arena_play", fake_play)
    rc = main(["arena", "play", "--token", "tok", "--lane", "rated"])
    assert rc == 0
    assert called["argv"] == ["--token", "tok", "--lane", "rated"]
    assert "agent-starter-kit" not in capsys.readouterr().err  # did NOT defer


@pytest.mark.parametrize(
    "argv",
    [
        ["arena", "--owner", "x@y.com"],
        ["arena", "--base-url", "https://agentdex.ai-builders.space"],
    ],
)
def test_arena_option_first_routes_to_defer(argv, capsys):
    # The footgun: an OPTION-first arena call (a flag with NO positional before it)
    # must still route to the defer stub, not argparse's exit-2 "unrecognized
    # arguments". nargs=REMAINDER alone fails this; main() intercepts it. PR #183 review.
    rc = main(argv)
    assert rc == 1
    assert "agent-starter-kit" in capsys.readouterr().err
