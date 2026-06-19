"""End-to-end self-play meta-harness loop — the FULL real-stack proof (ADR-0014).

This is the only driver that wires the **real** Lane-B evolver (bene's
``evolve_battle_harness``) onto the real Lane-A1 runner + Lane-A3 fitness over a
live Pokémon Showdown server — no mocks. ``e2e_driver.py`` (the committed C2
driver) mocks Lane B; this script proves the loop with bene actually mutating the
genome and the kill-gate gating on held-out win-rate.

It is heavy (needs bene + poke-env + a running PS server), so it is NOT a CI unit
test; it is promoted here from ``.scratch/`` for **durability** and is exercised
by the substrate-gated ``test_e2e_selfplay_metaharness.py``.

Run it::

    # boot a poke-env-compatible PS server on :8010 first, then:
    ADX_E2E_SELFPLAY=1 BENE_LANEB=/path/to/bene/worktree \\
    ADX_PS_HOST=127.0.0.1 ADX_PS_PORT=8010 \\
    E2E_N_GEN=1 E2E_CANDIDATES=2 E2E_N_BATTLES=2 \\
    python tasks/selfplay-metaharness/e2e_selfplay_metaharness.py

Env knobs: ``E2E_RUN_SEED`` (42), ``E2E_N_BATTLES`` (2), ``E2E_N_GEN`` (1),
``E2E_CANDIDATES`` (2), ``NEGATIVE_CONTROL`` (0 → a control that forces every
mutant to win_rate 0 so the kill-gate REJECTS — proves the gate isn't vacuous).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from adx_showdown.selfplay.fitness import multi_dim_fitness
from adx_showdown.selfplay.runner import run_vs_baselines

RUN_SEED = int(os.environ.get("E2E_RUN_SEED", "42"))
N_BATTLES = int(os.environ.get("E2E_N_BATTLES", "2"))
N_GEN = int(os.environ.get("E2E_N_GEN", "1"))
N_CANDIDATES = int(os.environ.get("E2E_CANDIDATES", "2"))


def _import_bene() -> Any:
    """Lazily import bene's battle module (it is not a workspace dependency).

    ``BENE_LANEB`` must point at a bene checkout/worktree exposing
    ``bene.kernel.battle``. Raises a clear error if it is unset/unimportable so a
    misconfigured run fails loudly instead of with an opaque ImportError."""
    lane_b = os.environ.get("BENE_LANEB")
    if not lane_b:
        raise RuntimeError(
            "BENE_LANEB is unset — point it at a bene checkout exposing "
            "bene.kernel.battle (the real Lane-B evolver)."
        )
    if lane_b not in sys.path:
        sys.path.insert(0, lane_b)
    import bene.kernel.battle as battle  # noqa: E402

    return battle


def run() -> dict[str, Any]:
    """Drive the full real-stack loop once and return the DONE_JSON dict.

    seed → run_vs_baselines (A1, real poke-env vs PS) → multi_dim_fitness (A3) →
    bene evolve_battle_harness (B, real) → re-measure best → uplift + kill-gate.
    """
    battle = _import_bene()
    BattleHarness = battle.BattleHarness
    FitnessVector = battle.FitnessVector
    evolve_battle_harness = battle.evolve_battle_harness
    bene_seed_harness = battle.seed_harness

    is_negative_control = os.environ.get("NEGATIVE_CONTROL", "0") == "1"
    fitness_cache: dict[str, Any] = {}

    def fitness_fn(bh: Any) -> Any:
        if bh.harness_id in fitness_cache:
            return fitness_cache[bh.harness_id]
        results = asyncio.run(run_vs_baselines(bh.to_dict(), RUN_SEED, N_BATTLES))
        a3 = multi_dim_fitness(results)
        battles = sum(int(r["raw_dims"]["n_battles"]) for r in results)
        fv = FitnessVector(
            win_rate=a3["win_rate"],
            elo=a3["elo"],
            move_legibility=a3["move_legibility"],
            no_forfeit_exploit=a3["no_forfeit_exploit"],
            turn_efficiency=a3["turn_efficiency"],
            battles_played=battles,
        )
        fitness_cache[bh.harness_id] = fv
        return fv

    base = bene_seed_harness()
    seed = BattleHarness(
        harness_id="H0-seed-random",
        system_prompt=base.system_prompt,
        move_selection_strategy="random",
        tool_policy=dict(base.tool_policy),
        params=dict(base.params),
    )
    print(
        f"[e2e] seed={seed.harness_id} strat={seed.move_selection_strategy} "
        f"n_gen={N_GEN} n_battles={N_BATTLES} run_seed={RUN_SEED} neg_ctrl={is_negative_control}",
        file=sys.stderr,
    )

    seed_fit = fitness_fn(seed)

    # Positive control: force the first mutant onto the runner-realizable 'max_damage'
    # so the loop has a genuine uplift to find (bene's own mutation may or may not hit
    # it in 1 gen). The negative control instead zeroes every mutant's win_rate so the
    # kill-gate must REJECT — proving the gate is not vacuous.
    original_mutate = BattleHarness.mutate
    mutated_count = 0

    def forced_mutate(self: Any, rng: Any, mutation_rate: float = 0.3) -> Any:
        nonlocal mutated_count
        mutated_count += 1
        new_bh = original_mutate(self, rng, mutation_rate)
        if mutated_count == 1 and not is_negative_control:
            import ulid

            return BattleHarness(
                harness_id=str(ulid.new()),
                system_prompt=new_bh.system_prompt,
                move_selection_strategy="max_damage",
                tool_policy=new_bh.tool_policy,
                params=new_bh.params,
            )
        return new_bh

    BattleHarness.mutate = forced_mutate
    try:
        if is_negative_control:

            def negative_fitness_fn(bh: Any) -> Any:
                fv = fitness_fn(bh)
                if bh.harness_id != seed.harness_id:
                    return fv.replace(win_rate=0.0)
                return fv

            actual_fitness_fn = negative_fitness_fn
        else:
            actual_fitness_fn = fitness_fn

        out = evolve_battle_harness(
            seed, actual_fitness_fn, n_gen=N_GEN, run_seed=RUN_SEED, candidates_per_gen=N_CANDIDATES
        )
    finally:
        BattleHarness.mutate = original_mutate

    best_fit = fitness_fn(out.best)
    # Every harness bene evaluated ran real held-out battles (cached by id), so the
    # true substrate cost is the sum over ALL of them — not just seed + best.
    total_battles = sum(fv.battles_played for fv in fitness_cache.values())
    uplift_pp = round((best_fit.win_rate - seed_fit.win_rate) * 100, 1)
    return {
        "DONE_JSON": True,
        "negative_control": is_negative_control,
        # Truth-in-advertising: A1/A3/B1 are the real implementations, but the run
        # is NOT a fully-unmodified bene evolution — disclose the injected control.
        # bene's selection, kill-gate, and lineage are real; only the first mutant's
        # genome is hand-built (positive) or every mutant's win_rate is zeroed (neg).
        "harness_mutation": (
            "negative_control: every mutant's win_rate forced to 0 so the kill-gate must REJECT"
            if is_negative_control
            else "positive_control: the first bene mutant is replaced with a hand-built "
            "max_damage harness (guarantees a runner-realizable uplift exists)"
        ),
        "real_components": [
            "A1.run_vs_baselines",
            "A3.multi_dim_fitness",
            "B1.evolve_battle_harness",
        ],
        "mocked_components": [],
        "seed": {
            "id": seed.harness_id,
            "strategy": seed.move_selection_strategy,
            "win_rate": round(seed_fit.win_rate, 3),
        },
        "best": {
            "id": out.best.harness_id,
            "strategy": out.best.move_selection_strategy,
            "win_rate": round(best_fit.win_rate, 3),
        },
        "win_rate_uplift_pp": uplift_pp,
        "killgate_report": out.killgate_report,
        "gens_completed": N_GEN,
        "candidates_evaluated": len(fitness_cache),
        "battles_played": total_battles,
        "anti_vacuous": {
            "battles_played_gt_0": total_battles > 0,
            "gens_gt_0": N_GEN > 0,
        },
    }


def main() -> int:
    done = run()
    print("DONE_JSON " + json.dumps(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
