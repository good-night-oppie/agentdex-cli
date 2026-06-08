"""adx assist — registry + router tests (no live LLM dependency)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agentdex_cli.assist import (
    AssistDecision,
    AssistRegistry,
    load_registry,
    route,
)
from agentdex_cli.assist.registry import Skill, Workflow


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_registry_loads_expected_ids():
    registry = load_registry()
    workflow_ids = {w.id for w in registry.list_workflows()}
    skill_ids = {s.id for s in registry.list_skills()}
    assert "expedition.nvidia" in workflow_ids
    assert "expedition.nvidia.mocked" in workflow_ids
    assert "bridge.probe" in skill_ids
    assert "langfuse.up" in skill_ids
    assert "langfuse.down" in skill_ids
    assert "langfuse.status" in skill_ids


def test_explicit_workflow_resolves_command():
    registry = load_registry()
    res = route(
        registry,
        prompt=None,
        explicit=("workflow", "expedition.nvidia.mocked"),
        explicit_args={"output": "expeditions/out-001/"},
    )
    assert res.used_llm is False
    decision = res.decision
    assert isinstance(decision, AssistDecision)
    assert decision.action == "workflow"
    assert decision.id == "expedition.nvidia.mocked"
    assert "--mocked" in decision.resolved_command
    assert "expeditions/out-001/" in decision.resolved_command


def test_explicit_skill_resolves_command():
    registry = load_registry()
    res = route(
        registry,
        prompt=None,
        explicit=("skill", "langfuse.status"),
    )
    assert res.decision.id == "langfuse.status"
    assert res.decision.resolved_command == ["adx", "langfuse", "status"]


def test_keyword_router_falls_through_when_llm_absent():
    registry = load_registry()
    res = route(registry, prompt="start docker compose for langfuse stack postgres clickhouse")
    # No ANTHROPIC_API_KEY in CI → falls through to keyword route.
    assert res.used_llm is False
    assert res.decision.action == "skill"
    assert res.decision.id == "langfuse.up"


def test_keyword_router_routes_mocked_expedition():
    registry = load_registry()
    res = route(
        registry,
        prompt="run a mocked nvidia expedition offline",
    )
    assert res.decision.id == "expedition.nvidia.mocked"


def test_assist_list_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "agentdex_cli.cli", "assist", "list"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0
    assert "expedition.nvidia" in proc.stdout
    assert "bridge.probe" in proc.stdout


def test_assist_run_dry_run_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "agentdex_cli.cli",
         "assist", "run", "skill", "langfuse.status", "--dry-run"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0
    assert "command:" in proc.stdout
    assert "adx langfuse status" in proc.stdout


def test_assist_ask_dry_run_smoke():
    proc = subprocess.run(
        [sys.executable, "-m", "agentdex_cli.cli",
         "assist", "ask", "bring up the trace stack", "--dry-run"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0
    assert "command:" in proc.stdout
