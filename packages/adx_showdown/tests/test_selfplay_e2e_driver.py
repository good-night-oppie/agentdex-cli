"""Tests for C2 — the e2e self-play driver: wiring, DONE_JSON shape, the
win-rate uplift 95% CI (SPEC DONE #3), anti-vacuous guards, the kill-gate, and
determinism. All run on the deterministic MOCK backend (no PS server); the real
poke-env backend is exercised by the committed artifact run, not unit tests."""

from __future__ import annotations

import json
import subprocess
import sys

from adx_showdown.harness import BattleHarness, seed_harness
from adx_showdown.selfplay.baselines import baseline_names
from adx_showdown.selfplay.e2e_driver import (
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
    assert r.battles_played == (1 + 2) * 3 * 30  # (seed + 2 gens) × 3 baselines × n
    assert r.gens_completed == 2


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
    # higher win_rate with every guard dim held → kept
    assert _is_pareto_improvement({**base, "win_rate": 0.7}, base) is True
    # no win_rate gain → never kept (even if a guard improves)
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
