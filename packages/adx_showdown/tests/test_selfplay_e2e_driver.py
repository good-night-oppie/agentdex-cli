"""Tests for C2 — the e2e self-play driver: wiring, DONE_JSON shape, the
win-rate uplift 95% CI (SPEC DONE #3), anti-vacuous guards, the kill-gate, and
determinism. All run on the deterministic MOCK backend (no PS server); the real
poke-env backend is exercised by the committed artifact run, not unit tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from adx_showdown.harness import BattleHarness, seed_harness
from adx_showdown.selfplay.baselines import baseline_names
from adx_showdown.selfplay.e2e_driver import (
    _CI_REMEASURE_SEED_OFFSET,
    _harness_id,
    _mock_evolve,
    _mock_run_vs_baselines,
    main,
    run_e2e,
    uplift_ci95,
)
from adx_showdown.selfplay.fitness import multi_dim_fitness


def _eval_fn(run_seed, n_battles):
    def f(h):
        res = _mock_run_vs_baselines(h, run_seed, n_battles)
        return res, multi_dim_fitness(res)

    return f


def _results(wins_per_baseline, n=30):
    return [
        {"raw_dims": {"opponent_baseline": b, "n_battles": n, "wins_a": w, "draws": 0}}
        for b, w in zip(baseline_names(), wins_per_baseline, strict=False)
    ]


def _controlled_results(win_frac, n):
    """A full Contract-2 result set at a chosen win fraction with every guard dim
    clean + constant (no forfeits/illegal moves, fixed turns) — so two harnesses
    differ only in win_rate (and the elo that tracks it). Lets a test drive the
    evolve keep/kill-gate + fresh-re-measure logic with exact win rates."""
    wins = round(n * win_frac)
    turns = n * 11
    return [
        {
            "winner": "a" if wins * 2 >= n else "b",
            "battles": [],
            "trace_path": "",
            "raw_dims": {
                "opponent_baseline": b,
                "n_battles": n,
                "wins_a": wins,
                "draws": 0,
                "turns": turns,
                "forfeits": 0,
                "illegal_moves": 0,
                "total_moves": turns,
            },
        }
        for b in baseline_names()
    ]


# ---- uplift 95% CI (closes SPEC DONE #3) ----


def test_ci_excludes_zero_on_large_clear_uplift():
    seed = _results([5, 4, 3], n=100)  # 12/300 = 4%
    best = _results([90, 80, 70], n=100)  # 240/300 = 80%
    ci = uplift_ci95(seed, best)
    assert ci["uplift_pp"] > 70
    assert ci["excludes_zero"] is True
    assert ci["ci95_pp"][0] > 0  # lower bound strictly positive


def test_ci_includes_zero_on_tiny_uplift_small_n():
    seed = _results([15, 15, 15], n=30)  # 50%
    best = _results([16, 16, 16], n=30)  # ~53%
    ci = uplift_ci95(seed, best)
    assert ci["excludes_zero"] is False  # 3pp over 90 battles is not significant


def test_ci_zero_battles_is_not_significant():
    ci = uplift_ci95([], [])
    assert ci["excludes_zero"] is False
    assert ci["n_seed"] == 0


def test_ci_uplift_matches_winrate_difference():
    seed = _results([10, 10, 10], n=30)  # 1/3
    best = _results([20, 20, 20], n=30)  # 2/3
    ci = uplift_ci95(seed, best)
    assert ci["uplift_pp"] == (2 / 3 - 1 / 3) * 100


# ---- DONE_JSON shape ----


def test_done_json_has_ci_fields():
    done = run_e2e(run_seed=42, n_gen=2, n_battles=200).to_done_json()
    assert set(done) >= {
        "ok",
        "lane",
        "backend",
        "scaffold",
        "battles_played",
        "gens_completed",
        "n_battles_per_matchup",
        "seed_fitness",
        "best_fitness",
        "win_rate_uplift_pp",
        "win_rate_uplift_ci95_pp",
        "ci_excludes_zero",
        "killgate",
        "lineage",
        "held_out_baselines",
        "run_seed",
        "mocked_components",
        "real_components",
        "note",
    }
    assert done["lane"] == "C2"
    assert done["backend"] == "mock"
    assert len(done["win_rate_uplift_ci95_pp"]) == 2


def test_mock_backend_marks_runner_mocked_genome_fitness_real():
    done = run_e2e().to_done_json()
    assert done["scaffold"] is True  # mock backend is a scaffold run
    assert any("runner" in m for m in done["mocked_components"])
    assert any("evolve" in m for m in done["mocked_components"])
    assert any("genome" in r and "A2" in r for r in done["real_components"])
    assert any("fitness" in r and "A3" in r for r in done["real_components"])


def test_held_out_baselines_are_the_three_real_ones():
    done = run_e2e().to_done_json()
    assert done["held_out_baselines"] == [
        "RandomPlayer",
        "MaxBasePowerPlayer",
        "SimpleHeuristicsPlayer",
    ]


# ---- anti-vacuous + ok criterion (DONE #3: ok requires CI excludes 0) ----


def test_ok_requires_ci_excludes_zero():
    big = run_e2e(run_seed=42, n_gen=3, n_battles=400, margin_pp=5.0)
    assert big.ci_excludes_zero is True
    assert big.ok is True
    # tiny n → CI includes 0 → ok False even with margin satisfied
    small = run_e2e(run_seed=42, n_gen=3, n_battles=3, margin_pp=0.0)
    assert small.ci_excludes_zero is False
    assert small.ok is False


def test_anti_vacuous_counts_positive():
    r = run_e2e(run_seed=7, n_gen=2, n_battles=30)
    # (seed + 2 gens) evolve battles + (seed + best) fresh re-measure battles,
    # × 3 baselines × 30 each
    assert r.battles_played == ((1 + 2) + 2) * 3 * 30
    assert r.gens_completed == 2


def test_ok_requires_min_30_battles_per_matchup():
    # DONE #3 demands the uplift CI hold over >=30 battles/matchup; below the bar
    # ok must be False even if everything else passes.
    r = run_e2e(run_seed=42, n_gen=3, n_battles=20, margin_pp=5.0)
    assert r.n_battles_per_matchup == 20
    assert r.ok is False


def test_seed_strategy_is_recorded_and_classified():
    canonical = run_e2e(run_seed=42, n_gen=1, n_battles=200).to_done_json()
    assert canonical["seed_strategy"] == "canonical-H0"
    assert canonical["canonical_seed"] is True
    override = run_e2e(run_seed=42, n_gen=1, n_battles=200, seed_strategy="random").to_done_json()
    assert override["seed_strategy"] == "random"
    assert override["canonical_seed"] is False


def test_injected_runner_is_not_classified_as_real():
    # A wrapped/custom runner through the public seam must NOT claim a real PS run.
    def wrapped(h, run_seed, n_battles):
        return _mock_run_vs_baselines(h, run_seed, n_battles)

    done = run_e2e(run_seed=42, n_gen=1, n_battles=200, runner_fn=wrapped).to_done_json()
    assert done["backend"] == "custom"
    assert done["scaffold"] is True
    assert not any("poke-env vs PS server" in r for r in done["real_components"])
    assert any("INJECTED custom runner" in m for m in done["mocked_components"])


def test_seed_is_the_real_contract1_genome():
    r = run_e2e(run_seed=42, n_gen=1, n_battles=200)
    expected, _ = _eval_fn(42, 200)(seed_harness())
    assert r.seed_fitness == multi_dim_fitness(expected)
    assert isinstance(seed_harness(), BattleHarness)


# ---- kill-gate non-vacuous ----


def test_killgate_rejects_non_improving_run():
    r = run_e2e(run_seed=42, n_gen=2, n_battles=200, margin_pp=99.0)
    assert r.killgate["passed"] is False
    assert r.killgate["rejected"] is True
    assert r.ok is False


def test_mock_evolve_keeps_improvements_and_returns_results():
    seed = seed_harness()
    res = _mock_evolve(seed, _eval_fn(1, 200), n_gen=3, run_seed=1, n_battles=200, margin_pp=10.0)
    assert isinstance(res.best, BattleHarness)
    assert res.best_results and res.seed_results  # carries scored results for the CI
    seed_win = multi_dim_fitness(_mock_run_vs_baselines(seed, 1, 200))["win_rate"]
    assert all(e["win_rate"] > seed_win for e in res.lineage if e["kept"])
    assert res.gens_completed == 3


# ---- fresh-re-measure gate hardening (PR #342 review) ----


def test_ok_false_when_fresh_margin_below_required():
    """P1 (review #3440028645): ``ok`` must gate the margin on the FRESH
    re-measure, not the selection sample. A best that clears ``margin_pp`` on the
    (lucky) selection draw but lands a significant yet sub-margin uplift on the
    independent re-measure must NOT be ok — even though the kill-gate passed."""
    seed_id = seed_harness().harness_id

    def staged_runner(h, run_seed, n_battles):
        is_candidate = _harness_id(h) != seed_id
        is_fresh = run_seed >= _CI_REMEASURE_SEED_OFFSET
        if not is_candidate:
            frac = 0.50
        elif is_fresh:
            frac = 0.55  # fresh: +5pp (significant at n≈1200, below the 10pp margin)
        else:
            frac = 0.90  # selection: +40pp — clears the kill-gate by a wide margin
        return _controlled_results(frac, n_battles)

    r = run_e2e(run_seed=0, n_gen=1, n_battles=400, margin_pp=10.0, runner_fn=staged_runner)
    assert any(e["kept"] for e in r.lineage)  # a candidate WAS kept (best ≠ seed)
    assert r.killgate["passed"] is True  # selection-sample margin cleared (40pp)
    assert r.ci_excludes_zero is True  # the fresh uplift IS significant
    assert 0.0 < r.win_rate_uplift_pp < 10.0  # ...but below the required margin
    assert r.ok is False  # the fix: the fresh margin decides ok, not selection


def test_ok_false_on_control_run_when_best_is_seed():
    """P2 (review #3440028647): when evolution keeps no candidate, best IS the
    seed. Re-measuring the identical harness on two different fresh schedules must
    not let run-seed noise fabricate a significant uplift — both sides share one
    fresh schedule, so the uplift is truthfully ~0 and ok fails closed."""

    def noisy_runner(h, run_seed, n_battles):
        # Candidate never raises win_rate (→ never kept → best stays the seed), but
        # win-rate is nudged by run-seed parity so an UNPAIRED fresh schedule
        # (seed vs seed+1) would manufacture a +6pp significant uplift from noise.
        frac = 0.50 + (0.06 if run_seed % 2 == 1 else 0.0)
        return _controlled_results(frac, n_battles)

    r = run_e2e(run_seed=0, n_gen=2, n_battles=400, margin_pp=0.0, runner_fn=noisy_runner)
    assert not any(e["kept"] for e in r.lineage)  # nothing kept → best is the seed
    assert r.win_rate_uplift_pp == 0.0  # same fresh schedule → no fabricated uplift
    assert r.ci_excludes_zero is False
    assert r.ok is False


# ---- full-vector (Pareto) keep, not win_rate alone ----


def test_evolve_rejects_winrate_gain_that_sacrifices_a_guard_dim():
    from adx_showdown.selfplay.e2e_driver import _is_pareto_improvement

    base = {
        "win_rate": 0.5,
        "elo": 1000.0,
        "move_legibility": 1.0,
        "no_forfeit_exploit": 1.0,
        "turn_efficiency": 1.0,
    }
    # higher win_rate bought by tanking an anti-reward-hack guard dim → REJECTED
    hacked = {**base, "win_rate": 0.7, "no_forfeit_exploit": 0.6}
    assert _is_pareto_improvement(hacked, base) is False
    # higher AGGREGATE win_rate but lower elo (won easy matchups, lost the hard
    # one) → REJECTED (elo is a Contract-3 maximize dim too)
    assert _is_pareto_improvement({**base, "win_rate": 0.7, "elo": 950.0}, base) is False
    # higher win_rate with every other Pareto dim held → kept
    assert _is_pareto_improvement({**base, "win_rate": 0.7}, base) is True
    # no win_rate gain → never kept (even if a dim improves)
    assert _is_pareto_improvement({**base, "move_legibility": 1.0}, base) is False


# ---- strategy-ladder mutation (real-backend uplift seam) ----


def test_random_seed_evolves_to_max_damage():
    r = run_e2e(run_seed=42, n_gen=1, n_battles=200, seed_strategy="random")
    assert any(e["strategy"] == "max_damage" for e in r.lineage)


# ---- determinism ----


def test_mock_run_is_deterministic_in_run_seed():
    a = run_e2e(run_seed=123, n_gen=2, n_battles=200).to_done_json()
    b = run_e2e(run_seed=123, n_gen=2, n_battles=200).to_done_json()
    assert a == b


def test_mock_battle_noise_is_independent_of_harness_id():
    # A rename-only / metadata-only mutation (identical policy, different
    # harness_id) must NOT change the measured outcome — else the scaffold could
    # attribute uplift to ID-dependent jitter and clear the kill-gate from noise.
    base = seed_harness().model_dump()
    alpha = {**base, "harness_id": "alpha"}
    renamed = {**base, "harness_id": "alpha-renamed"}
    wins_alpha = [r["raw_dims"]["wins_a"] for r in _mock_run_vs_baselines(alpha, 42, 200)]
    wins_renamed = [r["raw_dims"]["wins_a"] for r in _mock_run_vs_baselines(renamed, 42, 200)]
    assert wins_alpha == wins_renamed


# ---- CLI ----


def test_main_mock_emits_done_json(capsys):
    rc = main(["--run-seed", "42", "--gens", "3", "--battles", "400", "--margin-pp", "5"])
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert out.startswith("DONE_JSON ")
    payload = json.loads(out[len("DONE_JSON ") :])
    assert payload["backend"] == "mock"
    assert payload["ci_excludes_zero"] is True
    assert rc == 0


def test_main_writes_artifact(tmp_path, capsys):
    artifact = tmp_path / "done.json"
    main(["--gens", "2", "--battles", "400", "--margin-pp", "5", "--artifact", str(artifact)])
    capsys.readouterr()
    assert artifact.exists()
    payload = json.loads(artifact.read_text())
    assert payload["lane"] == "C2"
    assert "win_rate_uplift_ci95_pp" in payload


# --------------------------------------------------------------------------- #
# GA-BENE-3: the REAL evolve backend (bene's evolve_battle_harness). Gated on
# BENE_LANEB (bene is not a workspace dep); uses the MOCK runner so it needs no
# PS server — only that bene is importable. The full poke-env real-stack proof
# lives in test_e2e_selfplay_metaharness.py + done_e2e_real_bene.json.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not os.environ.get("BENE_LANEB"),
    reason="real evolve backend needs BENE_LANEB pointing at a bene checkout",
)
def test_real_evolve_backend_runs_bene_and_attributes_components():
    lane = os.environ["BENE_LANEB"]
    if lane not in sys.path:
        sys.path.insert(0, lane)
    pytest.importorskip("bene.kernel.battle")

    report = run_e2e(
        run_seed=42, n_gen=2, n_battles=30, seed_strategy="random", evolve_backend="real"
    )
    done = report.to_done_json()

    # The real bene evolver is attributed as REAL, and evolve is no longer mocked.
    assert any("bene.evolve_battle_harness" in c for c in done["real_components"])
    assert not any("evolve" in m for m in done["mocked_components"])
    # A real, hash-locked kill-gate verdict + non-vacuous counters.
    assert done["killgate"]["verdict"] in {"ACCEPT", "REJECT", "VOID"}
    assert done["gens_completed"] == 2
    assert done["battles_played"] > 0
    # The runner is still the mock here, so this is NOT a real uplift claim.
    assert done["backend"] == "mock"


def test_mock_is_the_default_evolve_backend():
    """evolve_backend defaults to mock so CI (no bene) stays green + deterministic."""
    report = run_e2e(run_seed=42, n_gen=1, n_battles=30, seed_strategy="random")
    done = report.to_done_json()
    assert any("evolve(LaneB/Contract4, bene-core)" in m for m in done["mocked_components"])


def test_module_runs_as_script():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "adx_showdown.selfplay.e2e_driver",
            "--run-seed",
            "5",
            "--battles",
            "300",
        ],
        capture_output=True,
        text=True,
    )
    assert "DONE_JSON " in proc.stdout
    payload = json.loads(proc.stdout.split("DONE_JSON ", 1)[1].splitlines()[0])
    assert payload["backend"] == "mock"
