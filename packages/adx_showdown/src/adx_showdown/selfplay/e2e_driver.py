"""C2 — end-to-end self-play meta-harness driver (ADR-0014 / SPEC Lane C2).

Wires the whole loop the SPEC's DONE criterion requires:

    seed harness
      → self-play vs HELD-OUT baselines  → BattleResult[]   (Lane A1 runner)
      → multi_dim_fitness                → Pareto vector     (Lane A3 — REAL)
      → evolve ≥1 generation             → best harness      (Lane B)
      → re-measure best vs held-out      → uplift            (Lane A3 — REAL)
    emit DONE_JSON

This is the **scaffold**: the cross-lane wiring + the final `DONE_JSON` shape are
real and frozen here; the pieces other lanes still own are MOCKED behind clearly
named `_mock_*` seams and listed in `DONE_JSON.mocked_components`, so nobody
mistakes a scaffold run for a real result. The fitness IS the real Lane-A3
function, so the evolution loop already optimizes the production objective. As
A1 (runner), A2 (genome), and Lane B (evolve) land, swap each `_mock_*` for the
real import — the driver body and `DONE_JSON` shape do not change.

**Anti-vacuous (SPEC DONE criterion #4):** the driver asserts `battles_played > 0`
AND `gens_completed > 0`, and the mock kill-gate genuinely REJECTS a harness that
does not beat the seed on held-out — `kill-gate clean` is never asserted on an
empty run.

Run it:  ``python -m adx_showdown.selfplay.e2e_driver --run-seed 42``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

from adx_showdown.harness import BattleHarness, seed_harness
from adx_showdown.selfplay.baselines import HELD_OUT_BASELINES, baseline_names
from adx_showdown.selfplay.fitness import FitnessVector, multi_dim_fitness

# Components this scaffold still mocks (owned by other lanes). Surfaced in
# DONE_JSON so a reader knows exactly what is real vs synthetic. The A2 genome
# (Contract 1) has LANDED, so it is real here — only the runner (A1) and the
# evolve step (Lane B) remain mocked.
MOCKED_COMPONENTS = [
    "runner(A1/Contract2, adx-cli-7)",
    "evolve(LaneB/Contract4, bene-core)",
]
REAL_COMPONENTS = [
    "genome(A2/Contract1, adx_showdown.harness)",
    "fitness(A3/Contract3, adx-core)",
]


def _params(harness: BattleHarness | dict[str, Any]) -> dict[str, Any]:
    """The param dict of a harness, accepting the real ``BattleHarness`` model
    or its dict form."""
    if isinstance(harness, BattleHarness):
        return dict(harness.params)
    return dict(harness.get("params", {}))


def _harness_id(harness: BattleHarness | dict[str, Any]) -> str:
    return harness.harness_id if isinstance(harness, BattleHarness) else harness["harness_id"]


def _strength(harness: BattleHarness | dict[str, Any]) -> float:
    """Map a (real Contract-1) BattleHarness to a synthetic 0..1 win-rate dial
    for the mock runner: the base comes from the genome's own ``aggression``
    param (so the REAL genome fields drive the scaffold), and ``_mock_strength``
    — a scaffold-only knob the mock evolve adds — climbs on top. Both vanish when
    A1's real runner replaces ``_mock_run_vs_baselines``."""
    p = _params(harness)
    try:
        base = 0.4 + 0.2 * float(p.get("aggression", 0.5))  # 0.5 @0.5 … 0.6 @1.0
    except (TypeError, ValueError):
        base = 0.5
    bump = float(p.get("_mock_strength", 0.0) or 0.0)
    return max(0.0, min(1.0, base + bump))


# --------------------------------------------------------------------------- #
# Mock seams — replace each with the real lane import as it lands.
# --------------------------------------------------------------------------- #


def _det_unit(*parts: Any) -> float:
    """Deterministic value in [0,1) from the parts — the scaffold's stand-in for
    battle RNG, so a given (harness, baseline, run_seed) always yields the same
    outcome (the SPEC's (seed,inputLog) reproducibility, mocked)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _mock_run_vs_baselines(
    harness: BattleHarness | dict[str, Any], run_seed: int, n_battles: int
) -> list[dict[str, Any]]:
    """Mock of Contract-2: run the (real) ``harness`` vs every held-out baseline,
    return one BattleResult per matchup. DETERMINISTIC given (harness strength,
    baseline, run_seed). Outcomes are SYNTHETIC — clean legal play (no forfeits/
    illegal), realistic turn counts — until A1's real runner replaces this.
    """
    strength = _strength(harness)
    hid = _harness_id(harness)
    results: list[dict[str, Any]] = []
    names = baseline_names()
    # Map each baseline to a difficulty in [0,1] by its order (weakest first).
    for i, name in enumerate(names):
        difficulty = i / max(1, len(names) - 1)  # 0.0, 0.5, 1.0
        # logistic win prob: stronger harness + weaker opponent → more wins.
        p = 1.0 / (1.0 + math.exp(-6.0 * (strength - difficulty)))
        # Deterministic per-battle wins (no RNG module — hash-seeded jitter).
        jitter = (_det_unit(hid, name, run_seed) - 0.5) * 0.1
        wins = max(0, min(n_battles, round(n_battles * (p + jitter))))
        turns = n_battles * 11  # ~11 turns/battle, comfortably under target
        results.append(
            {
                "winner": "a" if wins * 2 >= n_battles else "b",
                "battles": [],
                "trace_path": f"/tmp/selfplay/{hid}_vs_{name}_{run_seed}.json",
                "raw_dims": {
                    "opponent_baseline": name,
                    "n_battles": n_battles,
                    "wins_a": wins,
                    "draws": 0,
                    "turns": turns,
                    "forfeits": 0,
                    "illegal_moves": 0,
                    "total_moves": turns,
                },
            }
        )
    return results


@dataclass
class EvolveResult:
    """Mock of Contract-4's return: best harness + lineage + kill-gate report."""

    best: BattleHarness
    lineage: list[dict[str, Any]]
    killgate_report: dict[str, Any]
    gens_completed: int
    battles_played: int = 0


def _mutate(harness: BattleHarness, *, gen: int, run_seed: int) -> BattleHarness:
    """Scaffold stand-in for bene's genome mutation: bump the ``_mock_strength``
    knob (the win-rate dial) on a copy of the REAL BattleHarness, re-validated
    through the Contract-1 model so the candidate is always a legal genome.
    Lane B replaces this with real ``system_prompt``/``params`` perturbation."""
    data = harness.model_dump()
    data["harness_id"] = f"gen{gen}-{run_seed}"
    bump = 0.12 * (1.0 - _det_unit("bump", gen, run_seed) * 0.3)
    data["params"] = {
        **data.get("params", {}),
        "_mock_strength": min(1.0, float(data.get("params", {}).get("_mock_strength", 0.0)) + bump),
    }
    return BattleHarness.model_validate(data)


def _mock_evolve(
    seed: BattleHarness,
    fitness_fn: Any,
    n_gen: int,
    run_seed: int,
    *,
    n_battles: int,
    margin_pp: float,
) -> EvolveResult:
    """Mock of Contract-4 evolve (Lane B). Each generation mutates the REAL
    BattleHarness genome and keeps the candidate only if its REAL Lane-A3 fitness
    beats the incumbent's win_rate — so the loop already optimizes the production
    objective on the production genome; only the battle outcomes are synthetic.

    The KILL-GATE is real logic: the final best is accepted only if it beats the
    SEED on held-out by ``margin_pp``; a non-improving run is REJECTED (this is
    what makes the gate non-vacuous — verified by a dedicated test)."""
    seed_fit = fitness_fn(seed)
    incumbent = seed
    incumbent_fit = seed_fit
    lineage: list[dict[str, Any]] = []
    battles = len(baseline_names()) * n_battles  # the seed's own evaluation

    for gen in range(1, max(1, n_gen) + 1):
        cand = _mutate(incumbent, gen=gen, run_seed=run_seed)
        cand_fit = fitness_fn(cand)
        battles += len(baseline_names()) * n_battles
        improved = cand_fit["win_rate"] > incumbent_fit["win_rate"]
        lineage.append(
            {
                "gen": gen,
                "harness_id": cand.harness_id,
                "win_rate": cand_fit["win_rate"],
                "kept": improved,
            }
        )
        if improved:
            incumbent, incumbent_fit = cand, cand_fit

    best_margin_pp = (incumbent_fit["win_rate"] - seed_fit["win_rate"]) * 100.0
    passed = best_margin_pp >= margin_pp
    killgate_report = {
        "passed": bool(passed),
        "margin_pp": best_margin_pp,
        "required_margin_pp": margin_pp,
        "seed_win_rate": seed_fit["win_rate"],
        "best_win_rate": incumbent_fit["win_rate"],
        # non-vacuous: the gate rejects best if it did not clear the margin.
        "rejected": not passed,
    }
    return EvolveResult(
        best=incumbent,
        lineage=lineage,
        killgate_report=killgate_report,
        gens_completed=max(1, n_gen),
        battles_played=battles,
    )


# --------------------------------------------------------------------------- #
# The driver (real wiring; mocks behind the seams above).
# --------------------------------------------------------------------------- #


@dataclass
class E2EReport:
    ok: bool
    battles_played: int
    gens_completed: int
    seed_fitness: FitnessVector
    best_fitness: FitnessVector
    win_rate_uplift_pp: float
    killgate: dict[str, Any]
    held_out_baselines: list[str]
    run_seed: int
    mocked_components: list[str] = field(default_factory=lambda: list(MOCKED_COMPONENTS))
    real_components: list[str] = field(default_factory=lambda: list(REAL_COMPONENTS))

    def to_done_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "lane": "C2",
            "scaffold": True,
            "battles_played": self.battles_played,
            "gens_completed": self.gens_completed,
            "seed_fitness": self.seed_fitness,
            "best_fitness": self.best_fitness,
            "win_rate_uplift_pp": self.win_rate_uplift_pp,
            "killgate": self.killgate,
            "held_out_baselines": self.held_out_baselines,
            "run_seed": self.run_seed,
            "mocked_components": self.mocked_components,
            "real_components": self.real_components,
            "note": (
                "scaffold: cross-lane wiring + DONE_JSON shape are final and the "
                "fitness is the real Lane-A3 function; battle outcomes are "
                "synthetic until A1 (runner) + Lane B (evolve) land — the uplift "
                "is NOT a real result yet"
            ),
        }


def run_e2e(
    *,
    run_seed: int = 42,
    n_gen: int = 1,
    n_battles: int = 30,
    margin_pp: float = 10.0,
) -> E2EReport:
    """Drive one end-to-end scaffold run and return the report.

    Uses the REAL Lane-A2 ``seed_harness`` genome + the REAL Lane-A3
    ``multi_dim_fitness`` as the evolution objective; the runner + evolve are
    labeled mocks. Asserts the run is non-vacuous (battles_played > 0 ∧
    gens_completed > 0)."""
    seed = seed_harness()  # real Contract-1 H0

    def fitness_of(h: BattleHarness | dict[str, Any]) -> FitnessVector:
        return multi_dim_fitness(_mock_run_vs_baselines(h, run_seed, n_battles))

    seed_fitness = fitness_of(seed)
    evolved = _mock_evolve(
        seed, fitness_of, n_gen, run_seed, n_battles=n_battles, margin_pp=margin_pp
    )
    best_fitness = fitness_of(evolved.best)
    uplift_pp = (best_fitness["win_rate"] - seed_fitness["win_rate"]) * 100.0

    battles_played = evolved.battles_played + len(baseline_names()) * n_battles  # + final eval
    gens_completed = evolved.gens_completed

    # Anti-vacuous guard (SPEC DONE #4): a run that proved nothing is not ok.
    non_vacuous = battles_played > 0 and gens_completed > 0
    ok = non_vacuous and bool(evolved.killgate_report.get("passed"))

    return E2EReport(
        ok=ok,
        battles_played=battles_played,
        gens_completed=gens_completed,
        seed_fitness=seed_fitness,
        best_fitness=best_fitness,
        win_rate_uplift_pp=uplift_pp,
        killgate=evolved.killgate_report,
        held_out_baselines=list(HELD_OUT_BASELINES),
        run_seed=run_seed,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-seed", type=int, default=42)
    ap.add_argument("--gens", type=int, default=1, help="evolution generations (>=1)")
    ap.add_argument("--battles", type=int, default=30, help="battles per baseline matchup")
    ap.add_argument(
        "--margin-pp",
        type=float,
        default=10.0,
        help="kill-gate: best must beat seed win-rate by this many pp on held-out",
    )
    args = ap.parse_args(argv)
    report = run_e2e(
        run_seed=args.run_seed,
        n_gen=args.gens,
        n_battles=args.battles,
        margin_pp=args.margin_pp,
    )
    print("DONE_JSON " + json.dumps(report.to_done_json()))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_e2e", "E2EReport", "EvolveResult", "main", "MOCKED_COMPONENTS"]
