"""Tests for C2 — the e2e self-play driver scaffold.

Asserts the cross-lane WIRING + the DONE_JSON shape (the parts that are final
now), the anti-vacuous guards (battles_played>0 ∧ gens_completed>0), that the
real Lane-A3 fitness is what drives evolution, that the kill-gate genuinely
REJECTS a non-improving run, and run determinism. The mocked components are
asserted to be honestly disclosed."""

from __future__ import annotations

import json
import subprocess
import sys

from adx_showdown.selfplay.e2e_driver import (
    MOCKED_COMPONENTS,
    _mock_evolve,
    _mock_run_vs_baselines,
    _mock_seed_harness,
    main,
    run_e2e,
)
from adx_showdown.selfplay.fitness import multi_dim_fitness

# ---- DONE_JSON shape + anti-vacuous ----


def test_run_e2e_emits_full_done_shape():
    done = run_e2e(run_seed=42, n_gen=2, n_battles=30).to_done_json()
    assert set(done) >= {
        "ok",
        "lane",
        "scaffold",
        "battles_played",
        "gens_completed",
        "seed_fitness",
        "best_fitness",
        "win_rate_uplift_pp",
        "killgate",
        "held_out_baselines",
        "run_seed",
        "mocked_components",
        "real_components",
        "note",
    }
    assert done["lane"] == "C2"
    assert done["scaffold"] is True


def test_anti_vacuous_battles_and_gens_positive():
    report = run_e2e(run_seed=7, n_gen=2, n_battles=30)
    assert report.battles_played > 0
    assert report.gens_completed == 2


def test_held_out_baselines_are_the_three_real_ones():
    done = run_e2e().to_done_json()
    assert done["held_out_baselines"] == [
        "RandomPlayer",
        "MaxBasePowerPlayer",
        "SimpleHeuristicsPlayer",
    ]


def test_mocked_components_honestly_disclosed():
    done = run_e2e().to_done_json()
    # the scaffold must NOT claim the unlanded lanes are real
    assert done["mocked_components"] == MOCKED_COMPONENTS
    assert any("genome" in m for m in done["mocked_components"])
    assert any("runner" in m for m in done["mocked_components"])
    assert any("evolve" in m for m in done["mocked_components"])
    # fitness is the one real component
    assert any("fitness" in r and "A3" in r for r in done["real_components"])


# ---- real fitness drives the loop ----


def test_fitness_in_report_is_the_real_a3_function():
    """seed_fitness in the report must equal multi_dim_fitness applied to the
    seed's mock battles — i.e. the driver uses the REAL A3 fitness, not a stub."""
    report = run_e2e(run_seed=42, n_gen=1, n_battles=30)
    seed = _mock_seed_harness()
    expected = multi_dim_fitness(_mock_run_vs_baselines(seed, 42, 30))
    assert report.seed_fitness == expected


def test_evolution_produces_measured_uplift():
    report = run_e2e(run_seed=42, n_gen=3, n_battles=30)
    # the mock evolve strengthens the harness, so best win_rate > seed win_rate
    assert report.best_fitness["win_rate"] >= report.seed_fitness["win_rate"]
    assert (
        report.win_rate_uplift_pp
        == (report.best_fitness["win_rate"] - report.seed_fitness["win_rate"]) * 100.0
    )


# ---- kill-gate is non-vacuous ----


def test_killgate_passes_on_improving_run():
    report = run_e2e(run_seed=42, n_gen=3, n_battles=30, margin_pp=5.0)
    assert report.killgate["passed"] is True
    assert report.killgate["rejected"] is False
    assert report.ok is True


def test_killgate_rejects_non_improving_run():
    """A harness that does not beat the seed by the margin must be REJECTED —
    the gate is not a rubber stamp. With an impossibly high margin, even the
    improved best fails the gate, so ok=False + rejected=True."""
    report = run_e2e(run_seed=42, n_gen=2, n_battles=30, margin_pp=99.0)
    assert report.killgate["passed"] is False
    assert report.killgate["rejected"] is True
    assert report.ok is False


def test_mock_evolve_keeps_only_improvements():
    seed = _mock_seed_harness()

    def fit(h):
        return multi_dim_fitness(_mock_run_vs_baselines(h, 1, 30))

    res = _mock_evolve(seed, fit, n_gen=3, run_seed=1, n_battles=30, margin_pp=10.0)
    # every kept lineage entry strictly improved win_rate over its predecessor
    kept = [e for e in res.lineage if e["kept"]]
    assert all(e["win_rate"] > seed_win for seed_win in [fit(seed)["win_rate"]] for e in kept)
    assert res.gens_completed == 3


# ---- determinism ----


def test_run_is_deterministic_in_run_seed():
    a = run_e2e(run_seed=123, n_gen=2, n_battles=30).to_done_json()
    b = run_e2e(run_seed=123, n_gen=2, n_battles=30).to_done_json()
    assert a == b


def test_seed_threads_into_battle_traces():
    # the run_seed must reach the (mock) battle layer — trace paths encode it, so
    # two seeds produce distinguishable, reproducible-per-seed run records.
    seed = _mock_seed_harness()
    r1 = _mock_run_vs_baselines(seed, 1, 30)
    r2 = _mock_run_vs_baselines(seed, 2, 30)
    assert r1[0]["trace_path"] != r2[0]["trace_path"]
    assert "_1.json" in r1[0]["trace_path"] and "_2.json" in r2[0]["trace_path"]


# ---- CLI entrypoint emits DONE_JSON ----


def test_main_prints_done_json(capsys):
    rc = main(["--run-seed", "42", "--gens", "2", "--battles", "30"])
    out = capsys.readouterr().out.strip()
    assert out.startswith("DONE_JSON ")
    payload = json.loads(out[len("DONE_JSON ") :])
    assert payload["lane"] == "C2"
    assert payload["battles_played"] > 0
    assert rc == 0  # improving run → ok


def test_module_runs_as_script():
    proc = subprocess.run(
        [sys.executable, "-m", "adx_showdown.selfplay.e2e_driver", "--run-seed", "5"],
        capture_output=True,
        text=True,
    )
    assert "DONE_JSON " in proc.stdout
    payload = json.loads(proc.stdout.split("DONE_JSON ", 1)[1].splitlines()[0])
    assert payload["scaffold"] is True
