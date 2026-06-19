"""A4 — selfplay_battle MCP tool input contract (Contract 2).

Covers the pure arg-validation/clamp helper (no gateway, no PS server) so the
genome contract codex must satisfy + the n_battles cap are verified in CI. The
live tool path (auth + run_selfplay_battle) is exercised by A1's runner tests +
the e2e loop."""

from __future__ import annotations

import pytest
from agentdex_arena.mcp_surface import _MAX_SELFPLAY_BATTLES, _validate_selfplay_args
from pydantic import ValidationError

_A = {"harness_id": "cand", "move_selection_strategy": "max_damage"}
_B = {"harness_id": "rng", "move_selection_strategy": "random"}


def test_valid_harnesses_parse():
    a, b, n = _validate_selfplay_args(_A, _B, 10)
    assert a.harness_id == "cand"
    assert b.move_selection_strategy == "random"
    assert n == 10


@pytest.mark.parametrize(
    "given,expected",
    [(1000, _MAX_SELFPLAY_BATTLES), (0, 1), (-5, 1), (1, 1), (50, 50), (51, 50)],
)
def test_n_battles_clamped(given, expected):
    _, _, n = _validate_selfplay_args(_A, _B, given)
    assert n == expected


def test_malformed_genome_rejected():
    with pytest.raises(ValidationError):
        _validate_selfplay_args({"harness_id": ""}, _B, 10)  # empty id
    with pytest.raises(ValidationError):
        _validate_selfplay_args({"harness_id": "x", "bogus": 1}, _B, 10)  # extra=forbid


def test_tool_is_importable():
    # @mcp.tool() must not shadow the module-level symbol the loop imports.
    from agentdex_arena import mcp_surface

    assert hasattr(mcp_surface, "selfplay_battle")
