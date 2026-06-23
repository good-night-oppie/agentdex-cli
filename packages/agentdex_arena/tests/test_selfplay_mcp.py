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


def test_opponent_label_is_derived_and_unspoofable():
    # A caller naming harness_b after a strong held-out baseline must NOT be able
    # to claim its Elo anchor: the label is derived + namespaced, never an anchor.
    from adx_showdown.selfplay.baselines import ANCHOR_ELO, baseline_names
    from agentdex_arena.mcp_surface import _selfplay_opponent_label, _validate_selfplay_args

    _, b, _ = _validate_selfplay_args(_A, {"harness_id": "SimpleHeuristicsPlayer"}, 10)
    label = _selfplay_opponent_label(b)
    assert label not in baseline_names()  # not a held-out baseline name
    assert label not in ANCHOR_ELO  # → multi_dim_fitness uses the neutral default anchor
    assert "SimpleHeuristicsPlayer" in label  # still informative for the trace


def test_tool_is_importable():
    # @mcp.tool() must not shadow the module-level symbol the loop imports.
    from agentdex_arena import mcp_surface

    assert hasattr(mcp_surface, "selfplay_battle")


def test_tool_exposes_mode_param():
    # GA-SELFPLAY-EVOLVE: the MCP surface MUST expose ``mode`` so callers can
    # drive the runner by arena mode (solo_bots|pvp|team|selfplay). Without
    # this, the documented arena entrypoint cannot use the bridge that
    # ``run_selfplay_battle`` exposes (Codex P2 on PR #485).
    import inspect

    from agentdex_arena import mcp_surface

    sig = inspect.signature(mcp_surface.selfplay_battle)
    assert "mode" in sig.parameters
    assert sig.parameters["mode"].default is None  # back-compat default
