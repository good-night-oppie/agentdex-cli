"""Self-play meta-harness surface (ADR-0014 + tasks/selfplay-metaharness/SPEC.md).

Lane A of the fleet work-order: the agentdex-cli arena self-play surface that
codex drives (MCP-first) and bene evolves. This subpackage holds the frozen
cross-lane glue + adx-core's pieces:

  - ``fitness``   — A3: ``multi_dim_fitness`` (Contract 3), the Pareto vector
                    {win_rate, elo, move_legibility, no_forfeit_exploit,
                    turn_efficiency} computed over held-out-baseline battles.
  - ``baselines`` — A3: the held-out poke-env baseline registry
                    (RandomPlayer / MaxBasePowerPlayer / SimpleHeuristicsPlayer)
                    + calibration anchor Elos.
  - ``e2e_driver``— C2: the seed→self-play→fitness→evolve→uplift driver that
                    emits ``DONE_JSON`` (mocks the not-yet-landed lanes, honestly).

Lane A's runner (A1) + genome (A2), owned by adx-cli-7, land alongside as
``runner`` / ``genome`` in this same subpackage. The fitness function consumes
the Contract-2 ``BattleResult`` as a plain dict, so it carries no hard
dependency on those unlanded modules.
"""

from adx_showdown.selfplay.runner import (
    SelfPlayResult,
    make_harness_player,
    run_selfplay_battle,
    run_vs_baselines,
)

__all__ = [
    "SelfPlayResult",
    "make_harness_player",
    "run_selfplay_battle",
    "run_vs_baselines",
]
