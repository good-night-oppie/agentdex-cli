"""Tests for ``adx run`` — the allocation loop (v3 MVP #2, F1+F2)."""

from __future__ import annotations

import argparse
import json
import os
import random
import stat

import pytest
from adx_frontier.candidate import FRONTIER_AXES
from agentdex_cli.run_cmd import (
    FrontierSeedLedger,
    allocate,
    cmd_run,
    fake_axes,
    max_cost_from_constraints,
    signature,
)


def _policy_file(tmp_path, *, constraints: str = "none", explore_rate: float = 0.0):
    p = tmp_path / "orchestration.yaml"
    p.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix/python\n  - refactor\n"
        "objective:\n  - correctness\n  - cost\n  - latency\n"
        "pool:\n  - m-a\n  - m-b\n  - m-c\n"
        f"constraints: {constraints}\n"
        f"explore_rate: {explore_rate}\n",
        encoding="utf-8",
    )
    return p


def test_signature_matches_head_keyword():
    jobs = ["bugfix/python", "refactor", "code-review"]
    assert signature("please FIX the Bugfix now", jobs) == "bugfix/python"
    assert signature("refactor this", jobs) == "refactor"
    assert signature("write a poem", jobs) == "default"


def test_fake_axes_deterministic_keys_and_ranges():
    a = fake_axes("m-a", "bugfix", "t")
    assert a == fake_axes("m-a", "bugfix", "t")
    assert set(a) == set(FRONTIER_AXES)
    assert 0.0 <= a["quality"] < 1.0
    assert 0.01 <= a["cost_dollar"] <= 0.60
    assert 5.0 <= a["wall_clock_sec"] <= 120.0
    assert fake_axes("m-a", "bugfix", "t") != fake_axes("m-b", "bugfix", "t")


def test_max_cost_from_constraints():
    assert max_cost_from_constraints("max $0.50/task") == 0.5
    assert max_cost_from_constraints("none") is None
    assert max_cost_from_constraints("") is None


def test_frontier_seed_ledger_round_trip_and_corrupt_skip(tmp_path):
    led = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    scores = {"quality": 0.8, "cost_dollar": 0.1, "wall_clock_sec": 20.0}
    led.append(signature="bugfix", model="m-a", scores=scores, ts="t1")
    with led.path.open("a", encoding="utf-8") as fh:
        fh.write("NOT-JSON\n")
    led.append(
        signature="bugfix",
        model="m-a",
        scores={"quality": 0.6, "cost_dollar": 0.2, "wall_clock_sec": 30.0},
        ts="t2",
    )
    recs = led.records("bugfix")
    assert len(recs) == 2
    means = led.mean_records("bugfix")
    assert len(means) == 1
    assert means[0].scores["quality"] == pytest.approx(0.7)
    assert means[0].scores["cost_dollar"] == pytest.approx(0.15)
    assert means[0].scores["wall_clock_sec"] == pytest.approx(25.0)
    assert means[0].measured_at_utc == "t2"


def test_best_model_honors_objective_and_flips(tmp_path):
    path = tmp_path / "seeds.jsonl"
    rows = [
        {
            "signature": "sig",
            "model": "high-q",
            "scores": {"quality": 0.95, "cost_dollar": 0.40, "wall_clock_sec": 30.0},
            "ts": "t",
        },
        {
            "signature": "sig",
            "model": "cheap",
            "scores": {"quality": 0.70, "cost_dollar": 0.05, "wall_clock_sec": 40.0},
            "ts": "t",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    led = FrontierSeedLedger(path)
    assert led.best_model("sig", ["correctness", "cost"], None) == "high-q"
    assert led.best_model("sig", ["cost", "correctness"], None) == "cheap"
    assert led.best_model("unseen", ["correctness"], None) is None


def test_mean_records_skips_poison_rows(tmp_path):
    """FIX-1: missing ts / NaN quality / negative cost must not brick best_model."""
    path = tmp_path / "seeds.jsonl"
    good = {
        "signature": "sig",
        "model": "good",
        "scores": {"quality": 0.9, "cost_dollar": 0.1, "wall_clock_sec": 20.0},
        "ts": "t-good",
    }
    no_ts = {
        "signature": "sig",
        "model": "poison-no-ts",
        "scores": {"quality": 0.99, "cost_dollar": 0.01, "wall_clock_sec": 10.0},
    }
    nan_quality = {
        "signature": "sig",
        "model": "poison-nan",
        "scores": {"quality": float("nan"), "cost_dollar": 0.01, "wall_clock_sec": 10.0},
        "ts": "t-nan",
    }
    neg_cost = {
        "signature": "sig",
        "model": "poison-neg",
        "scores": {"quality": 0.99, "cost_dollar": -1.0, "wall_clock_sec": 10.0},
        "ts": "t-neg",
    }
    # NaN must be written via allow_nan so json.loads reconstitutes it.
    lines = [
        json.dumps(good),
        json.dumps(no_ts),
        json.dumps(nan_quality, allow_nan=True),
        json.dumps(neg_cost),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    led = FrontierSeedLedger(path)
    assert led.best_model("sig", ["correctness", "cost"], None) == "good"
    means = led.mean_records("sig")
    assert [m.candidate for m in means] == ["good"]


def test_allocate_cold_start_fans_out():
    models, mode = allocate(["a", "b", "c"], None, 0.0, random.Random(0), fanout=2)
    assert mode == "cold-start-fanout"
    assert models == ["a", "b"]


def test_allocate_exploits_known_best_when_explore_zero():
    models, mode = allocate(["a", "b", "c"], "b", 0.0, random.Random(0), fanout=3)
    assert mode == "exploit"
    assert models == ["b"]


def test_allocate_explores_adds_non_incumbent():
    models, mode = allocate(["a", "b", "c"], "b", 1.0, random.Random(0), fanout=3)
    assert mode == "explore"
    assert models[0] == "b" and len(models) == 2 and models[1] != "b"


def test_cmd_run_learns_and_exports_frontier(tmp_path, capsys):
    policy = _policy_file(tmp_path)
    ledger = tmp_path / "seeds.jsonl"
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(ledger),
        engine="fake",
        fanout=3,
        seed=0,
        json=True,
    )
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert ledger.exists()
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    assert rows
    assert "scores" in rows[0]
    assert set(rows[0]["scores"]) == set(FRONTIER_AXES)
    frontier = tmp_path / "frontier.json"
    assert frontier.exists()
    payload = json.loads(frontier.read_text(encoding="utf-8"))
    ladders = {p["ladder_id"] for p in payload["partitions"]}
    assert "job:bugfix/python" in ladders
    assert '"winner"' in out
    led = FrontierSeedLedger(ledger)
    best_first = led.best_model("bugfix/python", ["correctness", "cost", "latency"], None)
    assert best_first is not None
    ns.task = "another bugfix"
    ns.json = False
    assert cmd_run(ns) == 0
    out2 = capsys.readouterr().out
    assert "exploit" in out2
    assert led.best_model("bugfix/python", ["correctness", "cost", "latency"], None) == best_first


def test_cmd_run_all_pruned_records_without_winner(tmp_path, capsys):
    policy = _policy_file(tmp_path, constraints="max $0.000001/task")
    ledger = tmp_path / "seeds.jsonl"
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(ledger),
        engine="fake",
        fanout=3,
        seed=0,
        json=True,
    )
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert "all candidates exceed max cost" in out
    assert ledger.exists()
    assert ledger.read_text(encoding="utf-8").strip()
    assert '"winner": null' in out


def test_cmd_run_max_zero_cost_exits_clean(tmp_path, capsys):
    """FIX-2: max $0/task must not crash on budget_usd=0.0 validation."""
    policy = _policy_file(tmp_path, constraints="max $0/task")
    ledger = tmp_path / "seeds.jsonl"
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(ledger),
        engine="fake",
        fanout=3,
        seed=0,
        json=True,
    )
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert '"winner": null' in out
    assert ledger.exists()
    assert ledger.read_text(encoding="utf-8").strip()


def test_cmd_run_comma_scalar_policy_fields_match_sequences(tmp_path, capsys):
    """FIX-3: comma-separated YAML scalars must behave like sequences."""
    seq = _policy_file(tmp_path)
    scalar = tmp_path / "scalar.yaml"
    scalar.write_text(
        "version: 1\n"
        "job_types: bugfix/python, refactor\n"
        "objective: correctness, cost, latency\n"
        "pool: m-a, m-b, m-c\n"
        "constraints: none\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    ledger_seq = tmp_path / "seq" / "seeds.jsonl"
    ledger_seq.parent.mkdir()
    ledger_scalar = tmp_path / "scalar" / "seeds.jsonl"
    ledger_scalar.parent.mkdir()
    ns_seq = argparse.Namespace(
        task="fix the bugfix",
        policy=str(seq),
        ledger=str(ledger_seq),
        engine="fake",
        fanout=3,
        seed=0,
        json=True,
    )
    ns_scalar = argparse.Namespace(
        task="fix the bugfix",
        policy=str(scalar),
        ledger=str(ledger_scalar),
        engine="fake",
        fanout=3,
        seed=0,
        json=True,
    )
    assert cmd_run(ns_seq) == 0
    out_seq = capsys.readouterr().out
    assert cmd_run(ns_scalar) == 0
    out_scalar = capsys.readouterr().out
    json_seq = json.loads([ln for ln in out_seq.splitlines() if ln.startswith("{")][-1])
    json_scalar = json.loads([ln for ln in out_scalar.splitlines() if ln.startswith("{")][-1])
    assert json_seq["signature"] == json_scalar["signature"] == "bugfix/python"
    assert json_seq["winner"] == json_scalar["winner"]
    assert json_seq["mode"] == json_scalar["mode"]


def test_bool_quality_skipped_by_mean_and_export(tmp_path):
    """FIX-4: bool axis values must not launder into perfect scores."""
    path = tmp_path / "seeds.jsonl"
    rows = [
        {
            "signature": "sig",
            "model": "bool-cheat",
            "scores": {"quality": True, "cost_dollar": 0.01, "wall_clock_sec": 5.0},
            "ts": "t-bool",
        },
        {
            "signature": "sig",
            "model": "honest",
            "scores": {"quality": 0.5, "cost_dollar": 0.2, "wall_clock_sec": 30.0},
            "ts": "t-honest",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    led = FrontierSeedLedger(path)
    assert led.best_model("sig", ["correctness", "cost"], None) == "honest"
    frontier_path = led.export_frontier()
    payload = json.loads(frontier_path.read_text(encoding="utf-8"))
    candidates = {rec["candidate"] for part in payload["partitions"] for rec in part["frontier"]}
    assert "bool-cheat" not in candidates
    assert "honest" in candidates


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory write permission checks")
def test_cmd_run_persistence_failure_prints_table_and_exits_1(tmp_path, capsys):
    """FIX-5: read-only ledger dir → exit 1 with table + could not persist, no traceback."""
    policy = _policy_file(tmp_path)
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    ledger = ro_dir / "seeds.jsonl"
    os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
    try:
        ns = argparse.Namespace(
            task="fix the bugfix",
            policy=str(policy),
            ledger=str(ledger),
            engine="fake",
            fanout=3,
            seed=0,
            json=True,
        )
        assert cmd_run(ns) == 1
        out = capsys.readouterr().out
        assert "q=" in out
        assert "could not persist ledger: PermissionError" in out
        assert "Traceback" not in out
        assert '"frontier": null' in out
        assert '"next_best": null' in out
        assert "learned" not in out
    finally:
        os.chmod(ro_dir, stat.S_IRWXU)


def test_export_frontier_dedupes_identical_runs(tmp_path, capsys):
    """FIX-6(a): identical exploit runs must not accumulate duplicate frontier entries."""
    policy = _policy_file(tmp_path)
    ledger = tmp_path / "seeds.jsonl"
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(ledger),
        engine="fake",
        fanout=3,
        seed=0,
        json=False,
    )
    assert cmd_run(ns) == 0
    capsys.readouterr()
    # Warm exploit: same (model, scores) each time for a fixed task+seed.
    ns.task = "another bugfix"
    for _ in range(3):
        assert cmd_run(ns) == 0
        capsys.readouterr()
    frontier = json.loads((tmp_path / "frontier.json").read_text(encoding="utf-8"))
    sig = "bugfix/python"
    partition = next(p for p in frontier["partitions"] if p["ladder_id"] == f"job:{sig}")
    # Collect (candidate, scores) from the partition's frontier list.
    entries = partition.get("frontier") or partition.get("records") or []
    keys = []
    for rec in entries:
        scores = rec.get("scores") or {}
        keys.append((rec.get("candidate") or rec.get("model"), tuple(sorted(scores.items()))))
    assert len(keys) == len(set(keys))


def test_cmd_run_missing_policy_is_clean_error(tmp_path, capsys):
    ns = argparse.Namespace(
        task="t",
        policy=str(tmp_path / "nope.yaml"),
        ledger=str(tmp_path / "s.jsonl"),
        engine="fake",
        fanout=3,
        seed=0,
        json=False,
    )
    assert cmd_run(ns) == 2
    out = capsys.readouterr().out
    assert "adx interview" in out
    assert "Traceback" not in out


_FAKE_SK = "sk-TESTFAKEabcdefghijklmnop"


def test_cmd_run_malformed_policy_rc2_no_token_no_traceback(tmp_path, capsys):
    policy = tmp_path / "orchestration.yaml"
    policy.write_text(f'pool: "{_FAKE_SK}\n', encoding="utf-8")
    ns = argparse.Namespace(
        task="t",
        policy=str(policy),
        ledger=str(tmp_path / "s.jsonl"),
        engine="fake",
        fanout=3,
        seed=0,
        json=False,
    )
    assert cmd_run(ns) == 2
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert _FAKE_SK not in combined
    assert "Traceback" not in combined
    assert "line" in combined and "column" in combined
