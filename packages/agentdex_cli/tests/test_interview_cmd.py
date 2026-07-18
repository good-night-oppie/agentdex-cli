"""Tests for ``adx interview`` — the orchestration-policy intake (MVP #1)."""

from __future__ import annotations

import argparse

import yaml
from agentdex_cli.interview_cmd import (
    ORCHESTRATION_QUESTIONS,
    _ask,
    cmd_interview,
    render_policy_yaml,
)


def test_non_interactive_uses_defaults():
    ans = _ask(ORCHESTRATION_QUESTIONS, non_interactive=True)
    assert set(ans) == {q.key for q in ORCHESTRATION_QUESTIONS}
    assert all(ans[q.key] == q.default for q in ORCHESTRATION_QUESTIONS)


def test_rendered_policy_is_valid_yaml_with_expected_shape():
    doc = yaml.safe_load(render_policy_yaml(_ask(ORCHESTRATION_QUESTIONS, non_interactive=True)))
    assert doc["version"] == 1
    assert "generated" in doc
    # list-valued fields become YAML sequences the allocator can iterate
    assert isinstance(doc["job_types"], list) and doc["job_types"]
    assert isinstance(doc["objective"], list) and doc["objective"]
    assert isinstance(doc["pool"], list) and doc["pool"]
    # scalar fields stay scalar
    assert isinstance(doc["gate"], str)
    assert isinstance(doc["explore_rate"], str | float | int)


def test_comma_answer_splits_into_list():
    doc = yaml.safe_load(render_policy_yaml({"job_types": "a, b ,c", "pool": "x"}))
    assert doc["job_types"] == ["a", "b", "c"]
    assert doc["pool"] == ["x"]


def test_yaml_scalar_quoting_survives_special_chars():
    # a gate command with a colon must not break the YAML
    doc = yaml.safe_load(render_policy_yaml({"gate": "pytest -q: fast"}))
    assert doc["gate"] == "pytest -q: fast"


def test_cmd_interview_writes_file(tmp_path):
    out = tmp_path / "nested" / "orchestration.yaml"
    rc = cmd_interview(argparse.Namespace(out=str(out), non_interactive=True))
    assert rc == 0
    assert out.exists()
    doc = yaml.safe_load(out.read_text())
    assert doc["version"] == 1
    assert doc["gate"] == "tests"
