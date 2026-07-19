"""Tests for ``adx interview`` — the orchestration-policy intake (MVP #1)."""

from __future__ import annotations

import argparse

import pytest
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
    assert isinstance(doc["explore_rate"], (str, float, int))


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
    rc = cmd_interview(argparse.Namespace(out=str(out), non_interactive=True, force=False))
    assert rc == 0
    assert out.exists()
    doc = yaml.safe_load(out.read_text())
    assert doc["version"] == 1
    assert doc["gate"] == "tests"


def test_cmd_interview_refuses_overwrite_without_force(tmp_path, capsys):
    out = tmp_path / "orchestration.yaml"
    sentinel = "SENTINEL_KEEP_ME_XYZ"
    out.write_text(f"# {sentinel}\nversion: 1\n", encoding="utf-8")
    rc = cmd_interview(argparse.Namespace(out=str(out), non_interactive=True, force=False))
    assert rc == 2
    captured = capsys.readouterr().out
    assert "refusing to overwrite" in captured
    assert str(out) in captured
    assert "--force" in captured
    assert sentinel in out.read_text(encoding="utf-8")


def test_cmd_interview_force_overwrites(tmp_path):
    out = tmp_path / "orchestration.yaml"
    out.write_text("# SENTINEL_OLD\nversion: 0\n", encoding="utf-8")
    rc = cmd_interview(argparse.Namespace(out=str(out), non_interactive=True, force=True))
    assert rc == 0
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert "SENTINEL_OLD" not in out.read_text(encoding="utf-8")
    assert doc["gate"] == "tests"


# --------------------------------------------------------------------------- #
# emitter quoting — allowlist, not blocklist (fleet review finding)
# --------------------------------------------------------------------------- #


def test_leading_dash_scalar_stays_parseable():
    """A bullet-style constraints answer must not emit invalid YAML.

    `- never opus` previously emitted `constraints: - never opus`, which PyYAML
    rejects; `adx interview` reported success and the NEXT `adx run` died at
    load_policy with rc 2.
    """
    doc = yaml.safe_load(
        render_policy_yaml(
            {
                "job_types": "bugfix",
                "objective": "correctness",
                "pool": "claude-opus",
                "gate": "pytest",
                "constraints": "- never opus",
                "explore_rate": "0.2",
            }
        )
    )
    assert doc["constraints"] == "- never opus"


def test_leading_dash_in_list_field_does_not_nest():
    """The silent-corruption twin: a list field must not become a nested list.

    `- claude-opus, deepseek` previously parsed as [['claude-opus'], 'deepseek'],
    which _policy_list stringified into a pool member literally named
    "['claude-opus']" — then dispatched as a model id, with no error anywhere.
    """
    doc = yaml.safe_load(
        render_policy_yaml(
            {
                "job_types": "bugfix",
                "objective": "correctness",
                "pool": "- claude-opus, deepseek",
                "gate": "pytest",
                "constraints": "none",
                "explore_rate": "0.2",
            }
        )
    )
    assert doc["pool"] == ["- claude-opus", "deepseek"]
    assert all(isinstance(p, str) for p in doc["pool"])


@pytest.mark.parametrize("value", ["yes", "no", "on", "off", "true", "false", "null", "~"])
def test_yaml11_reserved_words_round_trip_as_strings(value):
    """YAML 1.1 would coerce these to bool/None, changing the type run reads back."""
    doc = yaml.safe_load(
        render_policy_yaml(
            {
                "job_types": "bugfix",
                "objective": "correctness",
                "pool": "claude-opus",
                "gate": value,
                "constraints": "none",
                "explore_rate": "0.2",
            }
        )
    )
    assert doc["gate"] == value, f"{value!r} must survive as a string"


def test_ordinary_answers_are_not_over_quoted():
    """The allowlist must not make the emitted policy unreadable."""
    text = render_policy_yaml(
        {
            "job_types": "bugfix/python, refactor",
            "objective": "correctness, cost, latency",
            "pool": "claude-opus, claude-sonnet, deepseek",
            "gate": "pytest -q tests/",
            "constraints": "none",
            "explore_rate": "0.2",
        }
    )
    assert "- claude-opus\n" in text, "plain model names stay unquoted"
    assert '"claude-opus"' not in text
    doc = yaml.safe_load(text)
    assert doc["pool"] == ["claude-opus", "claude-sonnet", "deepseek"]
    assert doc["gate"] == "pytest -q tests/"
