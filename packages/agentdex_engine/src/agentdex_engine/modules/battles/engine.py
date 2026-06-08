"""Battle engine — drives two agents in parallel until both terminal.

Per ADR-0005: stops are checkpoints, takers unblock per-stop, Pareto
decides winner. MVP drives one leaf path per side (no forking from past).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import anyio

from agentdex_engine.modules.agents.models import AgentVersion
from agentdex_engine.modules.battles.result import BattleResult, Domination, Move, SideResult
from agentdex_engine.modules.battles.takers import TurnTaker
from agentdex_engine.modules.battles.tree import Branch, Checkpoint, TrajectoryTree
from agentdex_engine.modules.evolver.pareto import dominates
from agentdex_engine.modules.tasks.models import TaskContext
from agentdex_engine.modules.tasks.trivial import make_scorer
from agentdex_engine.shared.helios_adapter import CheckpointStore
from agentdex_engine.shared.protocols import AgentRunner


@dataclass
class BattleSide:
    side_id: str
    agent_version: AgentVersion
    runner: AgentRunner
    taker: TurnTaker


async def _drive_side(
    side: BattleSide,
    task: TaskContext,
    tree: TrajectoryTree,
    store: CheckpointStore,
    history: list[Move],
    side_started_at: float,
) -> tuple[str, int, float]:
    """Run one side to terminal, recording checkpoints + branches in `tree`.

    Returns (final_output, move_count, elapsed_s).
    """
    move_idx = 0
    parent_branch_id: str | None = None
    while True:
        output = await side.runner.run_until_stop(task, history)

        if output.is_terminal:
            final = side.runner.final_output or output.output_text
            return final, move_idx, time.perf_counter() - side_started_at

        assert output.stop_signal is not None, "non-terminal output must carry a stop_signal"
        state = {
            "side_id": side.side_id,
            "move_idx": move_idx,
            "agent_output": output.output_text,
            "stop": output.stop_signal.model_dump(),
        }
        state_hash = await store.put(state)
        cp = Checkpoint(
            id=str(uuid.uuid4()),
            battle_id=tree.battle_id,
            side_id=side.side_id,
            parent_branch_id=parent_branch_id,
            state_hash=state_hash,
            move_index=move_idx,
        )
        tree.add_checkpoint(cp)

        taker_response = await side.taker.respond(side.side_id, output.stop_signal, history)

        move = Move(
            side_id=side.side_id,
            turn_index=move_idx,
            stop=output.stop_signal,
            taker_response=taker_response,
            agent_output_text=output.output_text,
        )
        history.append(move)
        branch = Branch(id=str(uuid.uuid4()), from_checkpoint_id=cp.id, move=move)
        tree.add_branch(branch)
        parent_branch_id = branch.id

        side.runner.resume(taker_response)
        move_idx += 1

        if move_idx > 50:
            raise RuntimeError(
                f"side {side.side_id!r} exceeded MVP turn cap (50); something is looping"
            )


async def run_battle(
    task: TaskContext,
    side_a: BattleSide,
    side_b: BattleSide,
    store: CheckpointStore,
) -> tuple[BattleResult, TrajectoryTree]:
    battle_id = str(uuid.uuid4())
    tree = TrajectoryTree(battle_id=battle_id)
    history_a: list[Move] = []
    history_b: list[Move] = []
    started = time.perf_counter()

    results: dict[str, tuple[str, int, float]] = {}

    async def _run_a() -> None:
        results["a"] = await _drive_side(side_a, task, tree, store, history_a, started)

    async def _run_b() -> None:
        results["b"] = await _drive_side(side_b, task, tree, store, history_b, started)

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run_a)
        tg.start_soon(_run_b)

    scorer = make_scorer(task.scorer)
    a_final, a_moves, a_elapsed = results["a"]
    b_final, b_moves, b_elapsed = results["b"]

    a_scores = scorer.score(task, a_final, elapsed_s=a_elapsed)
    b_scores = scorer.score(task, b_final, elapsed_s=b_elapsed)

    objectives = scorer.objectives
    winner = dominates(a_scores, b_scores, objectives)

    return (
        BattleResult(
            battle_id=battle_id,
            task_id=task.id,
            side_a=SideResult(
                side_id=side_a.side_id,
                agent_version_id=side_a.agent_version.id,
                final_output=a_final,
                scores=a_scores,
                move_count=a_moves,
                elapsed_s=a_elapsed,
            ),
            side_b=SideResult(
                side_id=side_b.side_id,
                agent_version_id=side_b.agent_version.id,
                final_output=b_final,
                scores=b_scores,
                move_count=b_moves,
                elapsed_s=b_elapsed,
            ),
            winner=winner,
            objectives=objectives,
        ),
        tree,
    )


def _winner_label(d: Domination) -> str:
    if d == Domination.A_DOMINATES:
        return "A"
    if d == Domination.B_DOMINATES:
        return "B"
    return "TIE"
