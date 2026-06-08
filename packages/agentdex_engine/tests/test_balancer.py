"""3-tier fairness gate tests (process / resource / procedure)."""
from __future__ import annotations

import pytest

from agentdex_engine.balancer import ResourceBalancer
from agentdex_engine.cards import TaskCard
from agentdex_engine.manifest import (
    AgentManifest,
    FairnessReport,
    stock_manifest,
)


def _task_card() -> TaskCard:
    return TaskCard(
        id="nvidia-earnings-infographic-q3-fy2026",
        source_bundle_hash="9edcd1a12c51f1741d90fab7b733a2144f1831bf7d28a7ead3165052c66dc09c",
        environment_spec={"runtime": "test"},
        oracle_spec_ref="tasks/x/oracle/spec.yaml",
        budget_token_cap=200_000,
        budget_dollar_cap=5.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )


def test_stock_manifests_for_three_baselines():
    for name in ("claude", "codex", "manus"):
        m = stock_manifest(name)
        assert m.agent_id == name
        assert m.context_window_tokens >= 128_000
        assert m.max_output_tokens >= 1024


def test_three_stock_baselines_pass_under_3tier_default():
    """Stock manifests are intentionally heterogeneous; the 3-tier gate
    declares the envelope (UNION) + per-baseline jagged profile in the
    deltas, and does NOT block on capability differences alone."""
    ms = [stock_manifest(n) for n in ("claude", "codex", "manus")]
    report = ResourceBalancer().equalize(
        ms, _task_card(),
        expedition_id="exp",
        prompt_template_hash="abc123",
        turn_budget=1,
    )
    assert report.fairness_verdict in {"pass", "warn"}
    # Envelope is the UNION, not the intersection.
    bc = report.balanced_constraints
    assert bc.context_window_tokens == max(m.context_window_tokens for m in ms)
    assert bc.max_output_tokens == max(m.max_output_tokens for m in ms)
    # Process verdict: same prompt + oracle ref + turn budget → pass.
    assert report.process.verdict == "pass"
    # Procedure verdict: same trace parent + same schema → pass.
    assert report.procedure.verdict == "pass"


def test_resource_ratio_warn_does_not_block():
    """One baseline 100x cheaper → resource warn, but overall not fail."""
    rich = AgentManifest(
        agent_id="rich",
        model_id="m", context_window_tokens=200_000, max_output_tokens=16_000,
        tool_allowlist=["read"], latency_budget_sec=120.0,
        cost_ceiling_dollar=10.0, special_capabilities=["tool_calls"],
    )
    poor = AgentManifest(
        agent_id="poor",
        model_id="m", context_window_tokens=128_000, max_output_tokens=8_000,
        tool_allowlist=["read"], latency_budget_sec=120.0,
        cost_ceiling_dollar=0.10, special_capabilities=["tool_calls"],
    )
    report = ResourceBalancer().equalize(
        [rich, poor], _task_card(),
        expedition_id="exp",
        prompt_template_hash="hash",
        turn_budget=1,
    )
    assert report.resource.verdict == "warn"
    assert report.resource.cost_ratio_max == pytest.approx(100.0)
    assert report.fairness_verdict in {"warn", "pass"}
    # never blocks on resource warn unless explicitly asked
    assert report.fairness_verdict != "fail"


def test_resource_warn_can_block_when_configured():
    rich = AgentManifest(
        agent_id="rich",
        model_id="m", context_window_tokens=128_000, max_output_tokens=4_000,
        tool_allowlist=["read"], latency_budget_sec=120.0,
        cost_ceiling_dollar=10.0, special_capabilities=["tool_calls"],
    )
    poor = AgentManifest(
        agent_id="poor",
        model_id="m", context_window_tokens=128_000, max_output_tokens=4_000,
        tool_allowlist=["read"], latency_budget_sec=120.0,
        cost_ceiling_dollar=0.10, special_capabilities=["tool_calls"],
    )
    report = ResourceBalancer(block_on_resource_warn=True).equalize(
        [rich, poor], _task_card(),
        expedition_id="exp",
        prompt_template_hash="hash",
        turn_budget=1,
    )
    assert report.fairness_verdict == "fail"


def test_process_fails_when_oracle_ref_missing():
    tc = _task_card().model_copy(update={"oracle_spec_ref": ""})
    ms = [stock_manifest(n) for n in ("claude", "codex")]
    report = ResourceBalancer().equalize(
        ms, tc, expedition_id="exp",
        prompt_template_hash="hash", turn_budget=1,
    )
    assert report.process.verdict == "fail"
    assert report.fairness_verdict == "fail"


def test_procedure_fails_when_trace_parent_diverges():
    ms = [stock_manifest(n) for n in ("claude", "codex")]
    balancer = ResourceBalancer()
    proc = balancer.assess_procedure(same_trace_parent=False)
    assert proc.verdict == "fail"


def test_jagged_capabilities_declared_not_dropped():
    """Claude's stream_json + long_context capabilities appear in the union
    envelope and per-baseline `capabilities_dropped` discloses what each
    baseline LACKS — not what is removed from the run."""
    ms = [stock_manifest(n) for n in ("claude", "codex", "manus")]
    report = ResourceBalancer().equalize(
        ms, _task_card(), expedition_id="exp",
        prompt_template_hash="hash", turn_budget=1,
    )
    union_caps = report.balanced_constraints.intersected_capabilities
    assert "stream_json" in union_caps
    assert "browser_dom" in union_caps
    assert "long_context" in union_caps
    # codex / manus declare their gaps via the delta.
    assert "stream_json" in report.deltas["codex"].capabilities_dropped
    assert "long_context" in report.deltas["codex"].capabilities_dropped
    assert "stream_json" in report.deltas["manus"].capabilities_dropped


def test_fairness_report_pydantic_strict():
    ms = [stock_manifest(n) for n in ("claude", "codex")]
    report = ResourceBalancer().equalize(
        ms, _task_card(), expedition_id="exp",
        prompt_template_hash="hash", turn_budget=1,
    )
    payload = report.model_dump()
    with pytest.raises(Exception):
        FairnessReport.model_validate({**payload, "rogue_field": "x"})


def test_empty_manifests_raises():
    with pytest.raises(ValueError):
        ResourceBalancer().equalize(
            [], _task_card(), expedition_id="exp",
            prompt_template_hash="hash", turn_budget=1,
        )
