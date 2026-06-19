"""C2 — end-to-end self-play meta-harness driver (ADR-0014 / SPEC Lane C2).

Wires the whole loop the SPEC's DONE criterion requires:

    seed harness
      → self-play vs HELD-OUT baselines  → BattleResult[]   (Lane A1 runner)
      → multi_dim_fitness                → Pareto vector     (Lane A3 — REAL)
      → evolve ≥1 generation             → best harness      (Lane B)
      → re-measure best vs held-out      → uplift + 95% CI   (Lane A3 — REAL)
    emit DONE_JSON

**Two backends** (``--backend``):
  - ``pokeenv`` — the REAL Lane-A1 runner (``run_vs_baselines``) over poke-env vs
    a live PS server. This closes SPEC DONE criterion #3: the win-rate uplift
    (best − seed on held-out baselines) is reported with a **two-proportion 95%
    confidence interval**, and the run is only ``ok`` when that CI **excludes 0**
    over ≥30 battles/matchup.
  - ``mock`` (default) — a deterministic synthetic runner so the wiring, CI math,
    and DONE_JSON shape are unit-testable WITHOUT a PS server (CI has none).

Only the EVOLVE step (Lane B) is still mocked; ``mocked_components`` /
``real_components`` in DONE_JSON state exactly what was real for a given run.

**Anti-vacuous (SPEC DONE #4):** asserts ``battles_played > 0`` ∧
``gens_completed > 0``; the kill-gate genuinely REJECTS a best that fails the
margin; and for the real backend ``ok`` additionally requires the uplift CI to
exclude 0 — significance is never assumed.

Run it (real, against PS :8010):
    ADX_PS_PORT=8010 python -m adx_showdown.selfplay.e2e_driver \\
        --backend pokeenv --seed-strategy random --battles 30 \\
        --artifact tasks/selfplay-metaharness/artifacts/done_c2_pokeenv.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adx_showdown.harness import BattleHarness, seed_harness
from adx_showdown.selfplay.baselines import HELD_OUT_BASELINES, baseline_names
from adx_showdown.selfplay.fitness import FitnessVector, multi_dim_fitness

# A runner: (harness, run_seed, n_battles) -> list of Contract-2 BattleResult dicts.
RunnerFn = Callable[[Any, int, int], list[dict[str, Any]]]

_Z95 = 1.959963984540054  # two-sided 95% normal quantile
_DONE3_MIN_BATTLES = 30  # SPEC DONE #3: the uplift CI must hold over >=30 battles/matchup
# The selected best is re-measured on FRESH held-out samples (run_seed offset by
# this) so the uplift CI is computed from data INDEPENDENT of the stochastic
# samples evolve selected on — not the selection samples themselves.
_CI_REMEASURE_SEED_OFFSET = 10_000


def _params(harness: BattleHarness | dict[str, Any]) -> dict[str, Any]:
    """The param dict of a harness, accepting the real ``BattleHarness`` model
    or its dict form."""
    if isinstance(harness, BattleHarness):
        return dict(harness.params)
    return dict(harness.get("params", {}))


def _strategy(harness: BattleHarness | dict[str, Any]) -> str:
    if isinstance(harness, BattleHarness):
        return harness.move_selection_strategy
    return str(harness.get("move_selection_strategy", "max_damage"))


def _harness_id(harness: BattleHarness | dict[str, Any]) -> str:
    return harness.harness_id if isinstance(harness, BattleHarness) else harness["harness_id"]


def _strength(harness: BattleHarness | dict[str, Any]) -> float:
    """Map a (real Contract-1) BattleHarness to a synthetic 0..1 win-rate dial
    for the MOCK runner: the base comes from the genome's own ``aggression``
    param, and ``_mock_strength`` — a scaffold-only knob the mock evolve adds —
    climbs on top. Irrelevant to the real runner (which reads
    ``move_selection_strategy``)."""
    p = _params(harness)
    try:
        base = 0.4 + 0.2 * float(p.get("aggression", 0.5))  # 0.5 @0.5 … 0.6 @1.0
    except (TypeError, ValueError):
        base = 0.5
    bump = float(p.get("_mock_strength", 0.0) or 0.0)
    return max(0.0, min(1.0, base + bump))


# --------------------------------------------------------------------------- #
# Runners — the real Lane-A1 backend + a deterministic mock for tests/CI.
# --------------------------------------------------------------------------- #


def pokeenv_runner(
    harness: BattleHarness | dict[str, Any], run_seed: int, n_battles: int
) -> list[dict[str, Any]]:
    """The REAL Lane-A1 runner: ``run_vs_baselines`` over poke-env vs a live PS
    server (point it with ``ADX_PS_HOST``/``ADX_PS_PORT``). Synchronous wrapper —
    the driver loop is sync; each call drives its own event loop. poke-env is
    imported lazily so the mock path stays poke-env-free."""
    from adx_showdown.selfplay.runner import run_vs_baselines

    return asyncio.run(run_vs_baselines(harness, run_seed, n_battles))


def _det_unit(*parts: Any) -> float:
    """Deterministic value in [0,1) from the parts — the MOCK runner's stand-in
    for battle RNG, so a given set of parts always yields the same outcome."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _mock_run_vs_baselines(
    harness: BattleHarness | dict[str, Any], run_seed: int, n_battles: int
) -> list[dict[str, Any]]:
    """Deterministic synthetic runner (Contract-2 shape) for tests/CI without a
    PS server. Win-rate scales with ``_strength`` (which folds in the genome's
    aggression + the mock evolve's ``_mock_strength``); clean legal play."""
    strength = _strength(harness)
    hid = _harness_id(harness)
    results: list[dict[str, Any]] = []
    names = baseline_names()
    for i, name in enumerate(names):
        difficulty = i / max(1, len(names) - 1)  # 0.0, 0.5, 1.0
        p = 1.0 / (1.0 + math.exp(-6.0 * (strength - difficulty)))
        # Battle noise is a property of the (baseline, run_seed) schedule, NOT the
        # harness identity. Seeding it on hid would let a rename-only / metadata
        # mutation shift win-rate and clear the kill-gate from ID noise rather than
        # a real policy change; keeping it id-independent also makes the jitter
        # cancel between seed and candidate, so the measured uplift is pure policy.
        jitter = (_det_unit(name, run_seed) - 0.5) * 0.1
        wins = max(0, min(n_battles, round(n_battles * (p + jitter))))
        turns = n_battles * 11
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


# --------------------------------------------------------------------------- #
# Win-rate uplift confidence interval (closes SPEC DONE #3).
# --------------------------------------------------------------------------- #


def _wins_and_battles(results: list[dict[str, Any]]) -> tuple[int, int]:
    """Total candidate wins (+ half-draws) and total battles across matchups."""
    wins = 0.0
    battles = 0
    for r in results:
        raw = r.get("raw_dims", {})
        wins += float(raw.get("wins_a", 0)) + 0.5 * float(raw.get("draws", 0))
        battles += int(raw.get("n_battles", 0))
    return wins, battles  # type: ignore[return-value]


def uplift_ci95(
    seed_results: list[dict[str, Any]], best_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Two-proportion (Wald) 95% CI on ``best_win_rate − seed_win_rate``.

    Closes SPEC DONE #3: ``excludes_zero`` is True only when the lower bound is
    strictly > 0, i.e. the evolved harness beats the seed on held-out with the
    uplift's 95% CI clear of zero. Returns pp (percentage-point) units."""
    sw, sn = _wins_and_battles(seed_results)
    bw, bn = _wins_and_battles(best_results)
    if sn == 0 or bn == 0:
        return {
            "uplift_pp": 0.0,
            "ci95_pp": [0.0, 0.0],
            "excludes_zero": False,
            "n_seed": sn,
            "n_best": bn,
            "seed_win_rate": 0.0,
            "best_win_rate": 0.0,
        }
    p1, p2 = sw / sn, bw / bn
    diff = p2 - p1
    se = math.sqrt(p1 * (1 - p1) / sn + p2 * (1 - p2) / bn)
    lo, hi = diff - _Z95 * se, diff + _Z95 * se
    return {
        "uplift_pp": diff * 100.0,
        "ci95_pp": [lo * 100.0, hi * 100.0],
        "excludes_zero": lo > 0.0,
        "n_seed": sn,
        "n_best": bn,
        "seed_win_rate": p1,
        "best_win_rate": p2,
    }


# --------------------------------------------------------------------------- #
# Evolve (mock of Lane B / Contract 4) — mutates the REAL genome.
# --------------------------------------------------------------------------- #


@dataclass
class EvolveResult:
    """Mock of Contract-4's return, carrying the scored results so the driver
    computes the CI without re-running battles."""

    best: BattleHarness
    best_fitness: FitnessVector
    best_results: list[dict[str, Any]]
    seed_fitness: FitnessVector
    seed_results: list[dict[str, Any]]
    lineage: list[dict[str, Any]]
    killgate_report: dict[str, Any]
    gens_completed: int
    battles_played: int = 0


def _mutate(harness: BattleHarness, *, gen: int, run_seed: int) -> BattleHarness:
    """Scaffold stand-in for bene's genome mutation, re-validated through the
    Contract-1 model so the candidate is always a legal genome. Two real knobs:

    - promote ``move_selection_strategy`` ``random`` → ``max_damage`` — the
      improvement the LANDED A1 runner actually realizes (it distinguishes those
      two; richer strategies are A1 follow-ups), so the REAL backend shows a
      genuine uplift; and
    - bump the ``_mock_strength`` dial the MOCK runner reads.

    Lane B replaces this with real ``system_prompt``/``params`` perturbation."""
    data = harness.model_dump()
    data["harness_id"] = f"gen{gen}-{run_seed}"
    if data.get("move_selection_strategy") == "random":
        data["move_selection_strategy"] = "max_damage"
    bump = 0.12 * (1.0 - _det_unit("bump", gen, run_seed) * 0.3)
    data["params"] = {
        **data.get("params", {}),
        "_mock_strength": min(1.0, float(data.get("params", {}).get("_mock_strength", 0.0)) + bump),
    }
    return BattleHarness.model_validate(data)


# Contract-3's other four maximize objectives — everything but win_rate. A
# candidate must not raise win_rate by regressing any of these: ``elo`` (rewards
# beating the STRONGER held-out baseline, so a candidate that trades hard-matchup
# wins for easy ones can lift aggregate win_rate while lowering elo) + the three
# anti-reward-hack guards. Compared with a small float-noise tolerance.
_NON_WINRATE_OBJECTIVES = ("elo", "move_legibility", "no_forfeit_exploit", "turn_efficiency")
_GUARD_TOL = 1e-9


def _is_pareto_improvement(cand: FitnessVector, incumbent: FitnessVector) -> bool:
    """Keep a candidate only if it raises ``win_rate`` AND regresses none of A3's
    other four Contract-3 dimensions (``elo`` + move_legibility / no_forfeit_exploit
    / turn_efficiency) — comparing the FULL five-dim Pareto vector, not win_rate
    alone. Otherwise the scaffold could 'evolve' a best that bought aggregate
    win-rate by sacrificing elo (winning easy matchups, losing the hard one) or
    gaming a guard dim down — exactly what A3's multi-dim fitness exists to catch."""
    if cand["win_rate"] <= incumbent["win_rate"]:
        return False
    return all(cand[d] >= incumbent[d] - _GUARD_TOL for d in _NON_WINRATE_OBJECTIVES)


def _mock_evolve(
    seed: BattleHarness,
    eval_fn: Callable[[BattleHarness], tuple[list[dict[str, Any]], FitnessVector]],
    n_gen: int,
    run_seed: int,
    *,
    n_battles: int,
    margin_pp: float,
) -> EvolveResult:
    """Mock of Contract-4 evolve (Lane B). Mutates the REAL genome and keeps a
    candidate only if its REAL Lane-A3 fitness is a Pareto improvement over the
    incumbent — higher win_rate with no regression on the anti-reward-hack guard
    dims (see :func:`_is_pareto_improvement`) — so the loop optimizes the full
    production objective, not win_rate in isolation. Each harness is evaluated
    exactly once (``eval_fn`` returns both the Contract-2 results and the
    fitness), so the driver can compute the uplift CI without re-running battles.
    The KILL-GATE is real logic: a best that fails to beat the seed by
    ``margin_pp`` is REJECTED.
    """
    seed_results, seed_fit = eval_fn(seed)
    incumbent, inc_fit, inc_results = seed, seed_fit, seed_results
    lineage: list[dict[str, Any]] = []
    n_baselines = len(baseline_names())
    battles = n_baselines * n_battles  # the seed's own evaluation

    for gen in range(1, max(1, n_gen) + 1):
        cand = _mutate(incumbent, gen=gen, run_seed=run_seed)
        cand_results, cand_fit = eval_fn(cand)
        battles += n_baselines * n_battles
        improved = _is_pareto_improvement(cand_fit, inc_fit)
        lineage.append(
            {
                "gen": gen,
                "harness_id": cand.harness_id,
                "strategy": cand.move_selection_strategy,
                "win_rate": cand_fit["win_rate"],
                "kept": improved,
            }
        )
        if improved:
            incumbent, inc_fit, inc_results = cand, cand_fit, cand_results

    best_margin_pp = (inc_fit["win_rate"] - seed_fit["win_rate"]) * 100.0
    passed = best_margin_pp >= margin_pp
    killgate_report = {
        "passed": bool(passed),
        "margin_pp": best_margin_pp,
        "required_margin_pp": margin_pp,
        "seed_win_rate": seed_fit["win_rate"],
        "best_win_rate": inc_fit["win_rate"],
        "rejected": not passed,
    }
    return EvolveResult(
        best=incumbent,
        best_fitness=inc_fit,
        best_results=inc_results,
        seed_fitness=seed_fit,
        seed_results=seed_results,
        lineage=lineage,
        killgate_report=killgate_report,
        gens_completed=max(1, n_gen),
        battles_played=battles,
    )


# --------------------------------------------------------------------------- #
# The driver.
# --------------------------------------------------------------------------- #


@dataclass
class E2EReport:
    ok: bool
    backend: str
    battles_played: int
    gens_completed: int
    n_battles_per_matchup: int
    seed_fitness: FitnessVector
    best_fitness: FitnessVector
    win_rate_uplift_pp: float
    win_rate_uplift_ci95_pp: list[float]
    ci_excludes_zero: bool
    killgate: dict[str, Any]
    lineage: list[dict[str, Any]]
    held_out_baselines: list[str]
    run_seed: int
    seed_strategy: str | None
    mocked_components: list[str]
    real_components: list[str]

    def to_done_json(self) -> dict[str, Any]:
        real_run = self.backend == "pokeenv"
        return {
            "ok": self.ok,
            "lane": "C2",
            "backend": self.backend,
            "scaffold": not real_run,
            # Disclose the seed: a non-canonical override (e.g. --seed-strategy
            # random) demonstrates uplift over THAT seed, not the canonical H0.
            "seed_strategy": self.seed_strategy or "canonical-H0",
            "canonical_seed": self.seed_strategy is None,
            "battles_played": self.battles_played,
            "gens_completed": self.gens_completed,
            "n_battles_per_matchup": self.n_battles_per_matchup,
            "seed_fitness": self.seed_fitness,
            "best_fitness": self.best_fitness,
            "win_rate_uplift_pp": self.win_rate_uplift_pp,
            "win_rate_uplift_ci95_pp": self.win_rate_uplift_ci95_pp,
            "ci_excludes_zero": self.ci_excludes_zero,
            "killgate": self.killgate,
            "lineage": self.lineage,
            "held_out_baselines": self.held_out_baselines,
            "run_seed": self.run_seed,
            "mocked_components": self.mocked_components,
            "real_components": self.real_components,
            "note": (
                "REAL run: poke-env Lane-A1 runner vs the held-out baselines on a "
                "live PS server; multi_dim_fitness (A3) + BattleHarness (A2) real; "
                "only the evolve step (Lane B) is mocked. The win-rate uplift is "
                "reported with a two-proportion 95% CI; ok requires the CI to "
                "exclude 0 (SPEC DONE #3)."
                if real_run
                else "MOCK backend: deterministic synthetic battles for testing "
                "the wiring + CI math + DONE_JSON shape without a PS server — the "
                "uplift is NOT a real result. Use --backend pokeenv for DONE #3."
            ),
        }


def _make_seed(strategy: str | None) -> BattleHarness:
    """The seed harness H0, optionally overriding ``move_selection_strategy`` so
    the real run can start from a weak ``random`` policy the evolution promotes
    (the runner-realizable improvement). ``None`` keeps the canonical H0."""
    s = seed_harness()
    if strategy and strategy != s.move_selection_strategy:
        s = s.model_copy(
            update={"move_selection_strategy": strategy, "harness_id": f"H0-{strategy}"}
        )
    return s


def run_e2e(
    *,
    run_seed: int = 42,
    n_gen: int = 1,
    n_battles: int = 30,
    margin_pp: float = 10.0,
    runner_fn: RunnerFn | None = None,
    seed_strategy: str | None = None,
) -> E2EReport:
    """Drive one end-to-end run and return the report.

    ``runner_fn`` defaults to the deterministic mock; pass ``pokeenv_runner`` for
    the real poke-env backend. Uses the REAL Lane-A2 genome + Lane-A3 fitness;
    only evolve is mocked. ``ok`` requires non-vacuous (battles>0 ∧ gens>0), a
    candidate that actually beat the seed (best ≠ seed), the kill-gate passed, AND
    the FRESH re-measure clearing both the margin (uplift_pp ≥ margin_pp) and
    significance (its 95% CI excludes 0, DONE #3) — the selection sample alone
    never decides ``ok``."""
    runner: RunnerFn = runner_fn or _mock_run_vs_baselines
    # Classify the runner EXPLICITLY: only the real pokeenv_runner is a PS-backed
    # run. A wrapped/injected runner through the public seam must not be able to
    # claim backend='pokeenv'/real — it is reported as 'custom' (a scaffold).
    if runner is pokeenv_runner:
        backend, real_run = "pokeenv", True
    elif runner is _mock_run_vs_baselines:
        backend, real_run = "mock", False
    else:
        backend, real_run = "custom", False
    seed = _make_seed(seed_strategy)

    def eval_fn(h: BattleHarness) -> tuple[list[dict[str, Any]], FitnessVector]:
        results = runner(h, run_seed, n_battles)
        return results, multi_dim_fitness(results)

    evolved = _mock_evolve(seed, eval_fn, n_gen, run_seed, n_battles=n_battles, margin_pp=margin_pp)

    # Re-measure seed + the SELECTED best on FRESH held-out samples (seeds offset so
    # the mock's deterministic results — and the live PS battles — are INDEPENDENT
    # of the stochastic samples evolve selected on). Computing the uplift CI from
    # the selection samples would let a lucky draw both pick the best AND clear the
    # CI, overstating the evidence; these battles are counted separately.
    remeasure_seed = run_seed + _CI_REMEASURE_SEED_OFFSET
    # When evolution kept NO candidate, the selected best IS the seed. Re-measuring
    # that identical harness on two different fresh schedules (remeasure_seed vs +1)
    # would let run-seed noise alone fabricate a positive, significant uplift. Use
    # the SAME fresh schedule for both sides in that case, so the uplift is
    # truthfully ~0 — and ``ok`` additionally fails closed below (review #3440028647).
    best_is_seed = _harness_id(evolved.best) == _harness_id(seed)
    fresh_seed_results = runner(seed, remeasure_seed, n_battles)
    best_remeasure_seed = remeasure_seed if best_is_seed else remeasure_seed + 1
    fresh_best_results = runner(evolved.best, best_remeasure_seed, n_battles)
    ci = uplift_ci95(fresh_seed_results, fresh_best_results)
    remeasure_battles = (
        _wins_and_battles(fresh_seed_results)[1] + _wins_and_battles(fresh_best_results)[1]
    )
    total_battles = evolved.battles_played + remeasure_battles

    non_vacuous = total_battles > 0 and evolved.gens_completed > 0
    ok = (
        non_vacuous
        # no candidate was kept → best is the seed → no improvement to claim
        and not best_is_seed
        and bool(evolved.killgate_report.get("passed"))
        # Gate the margin on the FRESH re-measure, not the selection sample: a run
        # can clear margin_pp on a lucky selection draw yet fall below it on the
        # independent re-measure that the reported uplift/CI come from — so trust
        # the fresh margin the report shows (review #3440028645).
        and ci["uplift_pp"] >= margin_pp
        and bool(ci["excludes_zero"])
        and n_battles >= _DONE3_MIN_BATTLES  # DONE #3: >=30 battles/matchup
    )

    mocked = ["evolve(LaneB/Contract4, bene-core)"]
    real = [
        "genome(A2/Contract1, adx_showdown.harness)",
        "fitness(A3/Contract3, adx-core)",
    ]
    if real_run:
        real.insert(1, "runner(A1/Contract2, poke-env vs PS server)")
    elif backend == "custom":
        mocked.insert(0, "runner(A1/Contract2 — INJECTED custom runner, not PS-backed)")
    else:
        mocked.insert(0, "runner(A1/Contract2 — mock synthetic backend)")

    return E2EReport(
        ok=ok,
        backend=backend,
        battles_played=total_battles,
        gens_completed=evolved.gens_completed,
        n_battles_per_matchup=n_battles,
        seed_fitness=evolved.seed_fitness,
        best_fitness=evolved.best_fitness,
        win_rate_uplift_pp=ci["uplift_pp"],
        win_rate_uplift_ci95_pp=ci["ci95_pp"],
        ci_excludes_zero=bool(ci["excludes_zero"]),
        killgate=evolved.killgate_report,
        lineage=evolved.lineage,
        held_out_baselines=list(HELD_OUT_BASELINES),
        run_seed=run_seed,
        seed_strategy=seed_strategy,
        mocked_components=mocked,
        real_components=real,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-seed", type=int, default=42)
    ap.add_argument("--gens", type=int, default=1, help="evolution generations (>=1)")
    ap.add_argument(
        "--battles", type=int, default=30, help="battles per baseline matchup (DONE #3: >=30)"
    )
    ap.add_argument(
        "--margin-pp",
        type=float,
        default=10.0,
        help="kill-gate: best must beat seed win-rate by this many pp on held-out",
    )
    ap.add_argument(
        "--backend",
        choices=["mock", "pokeenv"],
        default="mock",
        help="mock = deterministic synthetic; pokeenv = real run vs PS server",
    )
    ap.add_argument(
        "--seed-strategy",
        default=None,
        help="override the seed harness strategy (e.g. 'random' so the real run "
        "evolves random→max_damage, the runner-realizable uplift)",
    )
    ap.add_argument(
        "--artifact",
        default=None,
        help="write the DONE_JSON to this path (committed evidence, not stdout-only)",
    )
    args = ap.parse_args(argv)

    runner_fn = pokeenv_runner if args.backend == "pokeenv" else None
    report = run_e2e(
        run_seed=args.run_seed,
        n_gen=args.gens,
        n_battles=args.battles,
        margin_pp=args.margin_pp,
        runner_fn=runner_fn,
        seed_strategy=args.seed_strategy,
    )
    done = report.to_done_json()
    if args.artifact:
        path = Path(args.artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(done, indent=2) + "\n")
        print(f"[c2] wrote DONE_JSON artifact -> {args.artifact}")
    print("DONE_JSON " + json.dumps(done))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "run_e2e",
    "E2EReport",
    "EvolveResult",
    "main",
    "pokeenv_runner",
    "uplift_ci95",
]
