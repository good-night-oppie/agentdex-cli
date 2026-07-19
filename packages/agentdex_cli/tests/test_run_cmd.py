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


def test_allocate_cold_start_rotates_by_offset():
    """F6: repeated cold-starts with growing ledger cover later pool prefixes."""
    pool = ["a", "b", "c", "d"]
    m0, mode0 = allocate(pool, None, 0.0, random.Random(0), fanout=2, rotation=0)
    m2, mode2 = allocate(pool, None, 0.0, random.Random(0), fanout=2, rotation=2)
    assert mode0 == mode2 == "cold-start-fanout"
    assert m0 == ["a", "b"]
    assert m2 == ["c", "d"]
    assert m0 != m2


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
    entries = partition["frontier"]
    assert entries
    keys = []
    for rec in entries:
        scores = rec.get("scores") or {}
        keys.append((rec.get("candidate") or rec.get("model"), tuple(sorted(scores.items()))))
    assert len(keys) == len(set(keys))


def test_out_of_range_quality_never_wins(tmp_path):
    """C3: quality outside [0,1] must be skipped — honest candidate wins."""
    path = tmp_path / "seeds.jsonl"
    rows = [
        {
            "signature": "sig",
            "model": "poison-huge",
            "scores": {"quality": 1e9, "cost_dollar": 0.01, "wall_clock_sec": 5.0},
            "ts": "t-huge",
        },
        {
            "signature": "sig",
            "model": "poison-neg-q",
            "scores": {"quality": -0.5, "cost_dollar": 0.01, "wall_clock_sec": 5.0},
            "ts": "t-neg-q",
        },
        {
            "signature": "sig",
            "model": "honest",
            "scores": {"quality": 0.7, "cost_dollar": 0.2, "wall_clock_sec": 30.0},
            "ts": "t-honest",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    led = FrontierSeedLedger(path)
    assert led.best_model("sig", ["correctness", "cost"], None) == "honest"
    means = led.mean_records("sig")
    assert [m.candidate for m in means] == ["honest"]


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


# --------------------------------------------------------------------------- #
# bridges engine (mocked — no network)
# --------------------------------------------------------------------------- #


def _bridges_ns(tmp_path, *, fanout: int = 2, save_outputs=None, as_json: bool = True):
    policy = _policy_file(tmp_path)
    return argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(tmp_path / "seeds.jsonl"),
        engine="bridges",
        fanout=fanout,
        seed=0,
        json=as_json,
        max_tokens=2000,
        dispatch_timeout=180.0,
        save_outputs=str(save_outputs) if save_outputs is not None else None,
    )


def _fake_messages_response(*, model: str, input_tokens: int, output_tokens: int, text: str):
    return {
        "model": model,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def test_bridges_success_measures_axes_saves_json_ledger(tmp_path, capsys, monkeypatch):
    """Two models succeed → measured axes, adx-run-bridges receipts, saved outputs."""
    calls: list[str] = []

    def fake_post(base_url, *, model, task, max_tokens, timeout):
        calls.append(model)
        assert "127.0.0.1" in base_url or "localhost" in base_url
        # m-a cheaper (fewer tokens); equal quality → cost wins under objective.
        if model == "m-a":
            return _fake_messages_response(
                model=model, input_tokens=100, output_tokens=20, text="answer-a"
            )
        return _fake_messages_response(
            model=model, input_tokens=500, output_tokens=200, text="answer-b"
        )

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", fake_post)
    out_dir = tmp_path / "outs"
    ns = _bridges_ns(tmp_path, fanout=2, save_outputs=out_dir)
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert "neutral 0.5" in out
    assert "tok=" in out
    assert calls == ["m-a", "m-b"]

    ledger = tmp_path / "seeds.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 2
    assert all(r["receipt_kind"] == "adx-run-bridges" for r in rows)
    assert all(r["scores"]["quality"] == 0.5 for r in rows)

    assert (out_dir / "m-a.md").read_text(encoding="utf-8") == "answer-a"
    assert (out_dir / "m-b.md").read_text(encoding="utf-8") == "answer-b"
    assert "saved" in out

    payload = json.loads([ln for ln in out.splitlines() if ln.startswith("{")][-1])
    assert payload["engine"] == "bridges"
    assert payload["winner"] == "m-a"  # cheaper under equal quality
    assert len(payload["candidates"]) == 2
    by_model = {c["model"]: c for c in payload["candidates"]}
    assert by_model["m-a"]["tokens_in"] == 100
    assert by_model["m-a"]["tokens_out"] == 20
    assert by_model["m-a"]["output_file"].endswith("m-a.md")
    assert by_model["m-a"]["cost_dollar"] < by_model["m-b"]["cost_dollar"]


def test_bridges_one_model_urlerror_other_survives(tmp_path, capsys, monkeypatch):
    import urllib.error

    def fake_post(base_url, *, model, task, max_tokens, timeout):
        if model == "m-a":
            raise urllib.error.URLError("connection refused")
        return _fake_messages_response(model=model, input_tokens=50, output_tokens=10, text="ok-b")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", fake_post)
    ns = _bridges_ns(tmp_path, fanout=2)
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert "FAILED m-a: URLError" in out
    assert "connection refused" not in out  # type only — no body/message echo
    rows = [
        json.loads(line)
        for line in (tmp_path / "seeds.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rows) == 1
    assert rows[0]["model"] == "m-b"


def test_bridges_all_models_error_exits_1_no_ledger(tmp_path, capsys, monkeypatch):
    import urllib.error

    def fake_post(base_url, *, model, task, max_tokens, timeout):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", fake_post)
    ns = _bridges_ns(tmp_path, fanout=2)
    assert cmd_run(ns) == 1
    out = capsys.readouterr().out
    assert "all bridge candidates failed" in out
    assert not (tmp_path / "seeds.jsonl").exists()


def test_bridges_non_loopback_refuses_rc2_no_network(tmp_path, capsys, monkeypatch):
    called = {"n": 0}

    def fake_post(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("must not dispatch")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", fake_post)
    monkeypatch.setenv("ADX_BRIDGES_BASE_URL", "http://example.com:3456")
    ns = _bridges_ns(tmp_path, fanout=2)
    assert cmd_run(ns) == 2
    out = capsys.readouterr().out
    assert "non-loopback" in out
    assert called["n"] == 0
    assert not (tmp_path / "seeds.jsonl").exists()


# --------------------------------------------------------------------------- #
# PR #704 closure findings F1 / F2 / F4 / F5 / F6
# --------------------------------------------------------------------------- #


def test_policy_list_non_iterable_scalar_rc2_no_traceback(tmp_path, capsys):
    """F1: pool: true / objective: 1 → rc 2 clean message, no TypeError traceback."""
    cases = [
        "pool: true\n",
        "pool:\n  - m-a\nobjective: 1\n",
    ]
    for extra in cases:
        policy = tmp_path / "orchestration.yaml"
        policy.write_text(
            "version: 1\n"
            "job_types:\n  - bugfix\n"
            "objective:\n  - correctness\n"
            f"{extra}"
            "constraints: none\n"
            "explore_rate: 0.0\n",
            encoding="utf-8",
        )
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
        assert "policy field must be a list or comma-separated string" in combined
        assert "Traceback" not in combined
        assert "TypeError" not in combined


def test_cmd_run_unknown_objective_token_rc2(tmp_path, capsys):
    """F2: objective ['bogus'] → rc 2 naming bogus."""
    policy = tmp_path / "orchestration.yaml"
    policy.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix\n"
        "objective:\n  - bogus\n"
        "pool:\n  - m-a\n"
        "constraints: none\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
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
    out = capsys.readouterr().out
    assert "bogus" in out
    assert "Traceback" not in out


def test_cmd_run_cased_objective_tokens_ok(tmp_path, capsys):
    """F2: Latency/Cost/Correctness casefold to valid axes."""
    policy = tmp_path / "orchestration.yaml"
    policy.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix\n"
        "objective:\n  - Latency\n  - Cost\n  - Correctness\n"
        "pool:\n  - m-a\n  - m-b\n"
        "constraints: none\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(tmp_path / "s.jsonl"),
        engine="fake",
        fanout=2,
        seed=0,
        json=True,
    )
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert '"winner"' in out


def test_export_frontier_excludes_over_budget_rows(tmp_path):
    """F4: max_cost set → frontier.json drops rows above the ceiling."""
    path = tmp_path / "seeds.jsonl"
    rows = [
        {
            "signature": "sig",
            "model": "pricey",
            "scores": {"quality": 0.99, "cost_dollar": 0.40, "wall_clock_sec": 10.0},
            "ts": "t1",
        },
        {
            "signature": "sig",
            "model": "cheap",
            "scores": {"quality": 0.50, "cost_dollar": 0.01, "wall_clock_sec": 20.0},
            "ts": "t2",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    led = FrontierSeedLedger(path, max_cost=0.05)
    frontier_path = led.export_frontier()
    payload = json.loads(frontier_path.read_text(encoding="utf-8"))
    candidates = {rec["candidate"] for part in payload["partitions"] for rec in part["frontier"]}
    assert candidates == {"cheap"}
    assert "pricey" not in candidates


def test_bridges_pre_dispatch_cost_ceiling_skips_without_network(tmp_path, capsys, monkeypatch):
    """F5: max $0.0001/task + metered model → not dispatched, exit 3, urlopen never called."""
    called = {"n": 0}

    def fake_post(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("must not dispatch when over pre-dispatch ceiling")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", fake_post)
    policy = tmp_path / "orchestration.yaml"
    # claude-opus has nonzero rates in _RATE_TABLE
    policy.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix\n"
        "objective:\n  - correctness\n  - cost\n"
        "pool:\n  - claude-opus\n"
        "constraints: max $0.0001/task\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    ns = argparse.Namespace(
        task="fix the bugfix",
        policy=str(policy),
        ledger=str(tmp_path / "seeds.jsonl"),
        engine="bridges",
        fanout=1,
        seed=0,
        json=False,
        max_tokens=2000,
        dispatch_timeout=180.0,
        save_outputs=None,
    )
    assert cmd_run(ns) == 3
    out = capsys.readouterr().out
    assert "skipped claude-opus" in out
    assert "not dispatched" in out
    assert "no_feasible_candidate" in out
    assert called["n"] == 0
    assert not (tmp_path / "seeds.jsonl").exists()


def test_allocate_rotation_wraps_pool():
    """F6: rotation past end wraps deterministically."""
    pool = ["a", "b", "c"]
    models, mode = allocate(pool, None, 0.0, random.Random(0), fanout=2, rotation=2)
    assert mode == "cold-start-fanout"
    assert models == ["c", "a"]


# --------------------------------------------------------------------------- #
# F6 follow-up: rotation must survive rounds that append NOTHING
# --------------------------------------------------------------------------- #


def _pool5_policy(tmp_path, *, constraints: str = "none"):
    p = tmp_path / "orchestration.yaml"
    p.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix/python\n"
        "objective:\n  - correctness\n  - cost\n  - latency\n"
        "pool:\n  - m-a\n  - m-b\n  - m-c\n  - m-d\n  - m-e\n"
        f"constraints: {constraints}\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    return p


def test_cold_start_rotation_advances_when_every_dispatch_fails(tmp_path, monkeypatch):
    """The reviewer's actual withdraw condition, end-to-end.

    Every dispatch fails, so NO ledger rows are ever appended. A row-derived
    offset replays the same dead prefix forever; an attempt-derived one must
    still reach the later pool entries. Asserted on real dispatch attempts.
    """
    policy = _pool5_policy(tmp_path)
    attempted: list[str] = []

    def _explode(base_url, *, model, task, max_tokens, timeout):  # noqa: ANN001
        attempted.append(model)
        raise OSError("bridge down")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", _explode)

    for _ in range(3):
        ns = argparse.Namespace(
            task="t",
            policy=str(policy),
            ledger=str(tmp_path / "seeds.jsonl"),
            engine="bridges",
            fanout=2,
            seed=0,
            json=False,
            max_tokens=64,
            dispatch_timeout=5.0,
            save_outputs=None,
        )
        assert cmd_run(ns) == 1

    ledger = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    assert ledger._rows() == [], "precondition: failing rounds must append nothing"
    # 3 rounds x fanout 2 over a 5-model pool must reach every entry.
    assert set(attempted) == {"m-a", "m-b", "m-c", "m-d", "m-e"}, (
        f"rotation must cover the pool despite zero rows; got {attempted}"
    )


def test_bump_attempt_is_per_signature_and_monotonic(tmp_path):
    """Global counters alias mod len(pool) when signatures interleave."""
    led = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    a = [led.bump_attempt("sig-A") for _ in range(3)]
    b = [led.bump_attempt("sig-B") for _ in range(2)]
    assert a == [0, 1, 2], "per-signature count must not be perturbed by other sigs"
    assert b == [0, 1]
    reloaded = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    assert reloaded.bump_attempt("sig-A") == 3, "must persist across processes"


def test_bump_attempt_tolerates_corrupt_sidecar(tmp_path):
    led = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    led.attempts_path.parent.mkdir(parents=True, exist_ok=True)
    led.attempts_path.write_text("{not json", encoding="utf-8")
    assert led.bump_attempt("sig") == 0, "corrupt sidecar is advisory, never fatal"


def test_budget_prunes_pool_not_slice_so_affordable_model_still_runs(tmp_path, monkeypatch, capsys):
    """Probe-3 regression: an unaffordable prefix must not mask an affordable model.

    ceiling $0.01: claude-opus/claude-sonnet are over, deepseek is 4x under.
    Slice-pruning reported no_feasible_candidate; pool-pruning must dispatch
    deepseek instead.
    """
    p = tmp_path / "orchestration.yaml"
    p.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix/python\n"
        "objective:\n  - correctness\n  - cost\n  - latency\n"
        "pool:\n  - claude-opus\n  - claude-sonnet\n  - deepseek\n"
        "constraints: max $0.01/task\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def _fake_post(base_url, *, model, task, max_tokens, timeout):  # noqa: ANN001
        seen.append(model)
        return _fake_messages_response(model=model, input_tokens=10, output_tokens=5, text="ok")

    monkeypatch.setattr("agentdex_cli.run_cmd._post_messages", _fake_post)
    ns = argparse.Namespace(
        task="t",
        policy=str(p),
        ledger=str(tmp_path / "seeds.jsonl"),
        engine="bridges",
        fanout=2,
        seed=0,
        json=False,
        max_tokens=2000,
        dispatch_timeout=5.0,
        save_outputs=None,
    )
    rc = cmd_run(ns)
    out = capsys.readouterr().out
    assert "no_feasible_candidate" not in out, "affordable model exists — must not claim none"
    assert rc != 3
    assert "deepseek" in seen, f"affordable model must be dispatched, got {seen}"
    assert "claude-opus" not in seen, "over-budget model must never be dispatched"


def test_export_excludes_model_whose_MEAN_cost_is_over_budget(tmp_path):
    """F4 follow-up: raw-row filtering alone let one cheap run smuggle a model in.

    The allocator judges eligibility on mean-per-model records, so a model with
    runs at $0.000685 and $0.440135 (mean $0.22) is rejected by best_model under
    a $0.05 ceiling — but the export listed it on the strength of the cheap run.
    """
    seeds = tmp_path / "seeds.jsonl"
    seeds.parent.mkdir(parents=True, exist_ok=True)

    def _row(model: str, cost: float):
        return {
            "signature": "sig-1",
            "model": model,
            "scores": {"quality": 0.9, "cost_dollar": cost, "wall_clock_sec": 1.0},
            "ts": "2026-07-19T00:00:00Z",
            "receipt_kind": "adx-run-bridges",
        }

    seeds.write_text(
        "\n".join(
            json.dumps(r)
            for r in [_row("spiky", 0.000685), _row("spiky", 0.440135), _row("cheap", 0.001)]
        )
        + "\n",
        encoding="utf-8",
    )
    led = FrontierSeedLedger(seeds, max_cost=0.05)
    assert led.best_model("sig-1", ["correctness", "cost"], 0.05) == "cheap"

    out = json.loads(led.export_frontier().read_text(encoding="utf-8"))
    listed = json.dumps(out)
    assert "cheap" in listed
    assert "spiky" not in listed, (
        "a model the allocator rejects on mean cost must not be advertised"
    )


# --------------------------------------------------------------------------- #
# honesty guardrails for the scaffold ruling (issue #708)
# --------------------------------------------------------------------------- #


def _seed_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "signature": "bugfix",
                    "model": m,
                    "scores": {"quality": q, "cost_dollar": c, "wall_clock_sec": w},
                    "ts": "2026-07-19T00:00:00Z",
                    "receipt_kind": k,
                }
            )
            for m, q, c, w, k in rows
        )
        + "\n",
        encoding="utf-8",
    )


def test_simulated_rows_never_outrank_measured_ones(tmp_path):
    """Blocker 2 (#708): fake quality is a uniform hash draw, live is pinned 0.5.

    Pooling them let ~half of all synthetic rows structurally outrank EVERY real
    measurement — and `fake` is the DEFAULT engine, so a first run poisoned the
    ledger that drives real allocation.
    """
    seeds = tmp_path / "seeds.jsonl"
    _seed_rows(
        seeds,
        [
            ("model-A", 0.92, 0.40, 50.0, "adx-run-fake"),
            ("model-B", 0.50, 0.01, 1.0, "adx-run-bridges"),
        ],
    )
    led = FrontierSeedLedger(seeds)
    assert led.best_model("bugfix", ["correctness", "cost"], None) == "model-B"
    assert all(r.candidate == "model-B" for r in led.mean_records("bugfix"))


def test_simulated_only_ledger_still_usable(tmp_path):
    """With no measured rows, fake rows are all there is — do not blank the run."""
    seeds = tmp_path / "seeds.jsonl"
    _seed_rows(
        seeds,
        [
            ("model-A", 0.92, 0.40, 50.0, "adx-run-fake"),
            ("model-B", 0.10, 0.01, 1.0, "adx-run-fake"),
        ],
    )
    led = FrontierSeedLedger(seeds)
    assert led.best_model("bugfix", ["correctness", "cost"], None) == "model-A"


def test_constant_primary_axis_is_detected(tmp_path):
    """Blocker 1 (#708): a pinned primary axis makes the SHORTEST reply optimal."""
    seeds = tmp_path / "seeds.jsonl"
    _seed_rows(
        seeds,
        [
            ("did-real-work", 0.5, 0.0400, 42.0, "adx-run-bridges"),
            ("refused-instantly", 0.5, 0.0001, 0.3, "adx-run-bridges"),
        ],
    )
    led = FrontierSeedLedger(seeds)
    assert led.degenerate_primary_axis("bugfix", ["correctness", "cost", "latency"]) == "quality"
    # The winner is still the refusal — the guard reports, it does not re-rank.
    assert led.best_model("bugfix", ["correctness", "cost", "latency"], None) == "refused-instantly"


def test_no_false_alarm_when_primary_axis_varies(tmp_path):
    seeds = tmp_path / "seeds.jsonl"
    _seed_rows(
        seeds,
        [
            ("a", 0.9, 0.1, 1.0, "adx-run-bridges"),
            ("b", 0.4, 0.1, 1.0, "adx-run-bridges"),
        ],
    )
    led = FrontierSeedLedger(seeds)
    assert led.degenerate_primary_axis("bugfix", ["correctness", "cost"]) is None
