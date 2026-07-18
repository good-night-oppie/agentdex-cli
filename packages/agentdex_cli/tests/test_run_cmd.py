"""Tests for ``adx run`` — the allocation loop (v3 MVP #2)."""

from __future__ import annotations

import argparse
import random

from agentdex_cli.run_cmd import (
    Ledger,
    Seed,
    allocate,
    cmd_run,
    fake_score,
    signature,
)


def _policy_file(tmp_path):
    p = tmp_path / "orchestration.yaml"
    p.write_text(
        "version: 1\n"
        "job_types:\n  - bugfix/python\n  - refactor\n"
        "pool:\n  - m-a\n  - m-b\n  - m-c\n"
        "explore_rate: 0.0\n",
        encoding="utf-8",
    )
    return p


def test_signature_matches_head_keyword():
    jobs = ["bugfix/python", "refactor", "code-review"]
    assert signature("please FIX the Bugfix now", jobs) == "bugfix/python"
    assert signature("refactor this", jobs) == "refactor"
    assert signature("write a poem", jobs) == "default"


def test_fake_score_deterministic_and_model_signature_keyed():
    assert fake_score("m-a", "bugfix", "t") == fake_score("m-a", "bugfix", "t")
    # different model or signature → (almost surely) different score
    assert fake_score("m-a", "bugfix", "t") != fake_score("m-b", "bugfix", "t")


def test_ledger_best_model_is_highest_mean(tmp_path):
    led = Ledger(tmp_path / "seeds.jsonl")
    led.append(Seed("bugfix", "m-a", 0.9, "t"))
    led.append(Seed("bugfix", "m-b", 0.5, "t"))
    led.append(Seed("bugfix", "m-a", 0.7, "t"))  # mean m-a = 0.8 > m-b
    assert led.best_model("bugfix") == "m-a"
    assert led.best_model("unseen") is None


def test_allocate_cold_start_fans_out(tmp_path):
    led = Ledger(tmp_path / "seeds.jsonl")
    models, mode = allocate(["a", "b", "c"], "sig", led, 0.0, random.Random(0), fanout=2)
    assert mode == "cold-start-fanout"
    assert models == ["a", "b"]


def test_allocate_exploits_known_best_when_explore_zero(tmp_path):
    led = Ledger(tmp_path / "seeds.jsonl")
    led.append(Seed("sig", "b", 0.99, "t"))
    models, mode = allocate(["a", "b", "c"], "sig", led, 0.0, random.Random(0), fanout=3)
    assert mode == "exploit"
    assert models == ["b"]


def test_allocate_explores_adds_non_incumbent(tmp_path):
    led = Ledger(tmp_path / "seeds.jsonl")
    led.append(Seed("sig", "b", 0.99, "t"))
    models, mode = allocate(["a", "b", "c"], "sig", led, 1.0, random.Random(0), fanout=3)
    assert mode == "explore"
    assert models[0] == "b" and len(models) == 2 and models[1] != "b"


def test_cmd_run_learns_across_invocations(tmp_path, capsys):
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
    led = Ledger(ledger)
    best_first = led.best_model("bugfix/python")
    assert best_first is not None
    # second run of the same signature exploits (explore_rate 0.0 → 1 candidate)
    ns.task = "another bugfix"
    assert cmd_run(ns) == 0
    out = capsys.readouterr().out
    assert "exploit" in out
    assert led.best_model("bugfix/python") == best_first


def test_cmd_run_missing_policy_is_clean_error(tmp_path):
    ns = argparse.Namespace(
        task="t",
        policy=str(tmp_path / "nope.yaml"),
        ledger=str(tmp_path / "s.jsonl"),
        engine="fake",
        fanout=3,
        seed=0,
        json=False,
    )
    try:
        cmd_run(ns)
    except FileNotFoundError as exc:
        assert "adx interview" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing policy")
