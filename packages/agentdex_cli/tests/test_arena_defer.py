"""test_arena_defer — the deferred `adx arena` stub.

The arena surface (enroll / battle / evolution) is intentionally NOT wired into
the adx CLI; it is driven through the starter kit or the MCP endpoint. The stub
exists so a visiting agent typing `adx arena ...` gets actionable routing
instead of a bare argparse "invalid choice" error (ADX-P2-001 agent-ux footgun).

Tests:
1. `adx arena` parses to cmd_arena_defer (the subcommand exists at all).
2. Running it fails closed (rc=1) and prints starter-kit + MCP routing to stderr.
3. Arbitrary trailing args (`adx arena play --foo`) are swallowed by REMAINDER
   and still route cleanly — no argparse error on unknown sub-subcommands.
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
        ["arena", "play"],
        ["arena", "enroll", "--owner", "x@y.com"],
        ["arena", "battle", "--gym-leader", "gym-balance"],
    ],
)
def test_arena_swallows_trailing_args(argv, capsys):
    # REMAINDER must absorb any sub-args so the visiting agent never hits a
    # bare argparse "invalid choice" / "unrecognized arguments" error.
    rc = main(argv)
    assert rc == 1
    assert "agent-starter-kit" in capsys.readouterr().err
