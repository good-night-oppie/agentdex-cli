"""AgentManifest — per-baseline resource declaration for pre-Expedition fairness.

Per user direction 2026-06-08 "before expedition, we need a manifest for each
agent for balancing the resources they are separately using ... so they have
as close constraints and resources as possible".

Each baseline declares what it brings to the Expedition (model id, context
window, max output tokens, tool allowlist, latency budget, cost ceiling,
special capabilities). The :class:`ResourceBalancer` (``balancer.py``)
intersects these declarations to a single :class:`BalancedConstraints` so
no baseline races on an uneven playing field.

This is methodology, not nice-to-have: if Claude runs with 200K context but
Codex only sees 128K, the Pareto verdict is comparing apples to oranges.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CapabilityLiteral = Literal[
    "stream_json",
    "json_rpc_lite",
    "browser_dom",
    "subscription_quota",
    "api_quota",
    "tool_calls",
    "file_attach",
    "structured_output",
    "memory_persistence",
    "long_context",
]


class AgentManifest(BaseModel):
    """Resource declaration for one baseline in an Expedition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    agent_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    context_window_tokens: int = Field(ge=1024)
    max_output_tokens: int = Field(ge=1)
    tool_allowlist: list[str] = Field(default_factory=list)
    latency_budget_sec: float = Field(gt=0.0)
    cost_ceiling_dollar: float = Field(ge=0.0)
    special_capabilities: list[CapabilityLiteral] = Field(default_factory=list)
    auth_mode: Literal["subscription", "api_key", "browser_session"] = "subscription"
    notes: str | None = None


class BalancedConstraints(BaseModel):
    """The equalized resource envelope all baselines run inside."""

    model_config = ConfigDict(extra="forbid", strict=True)

    context_window_tokens: int = Field(ge=1024)
    max_output_tokens: int = Field(ge=1)
    tool_allowlist: list[str] = Field(default_factory=list)
    latency_budget_sec: float = Field(gt=0.0)
    cost_ceiling_dollar: float = Field(ge=0.0)
    intersected_capabilities: list[CapabilityLiteral] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class FairnessDelta(BaseModel):
    """Per-baseline deviation from the balanced envelope.

    Simplified to 3 fields after Musk-review: agent_id + two human-readable
    summary strings (``excess_summary`` = what this baseline has BEYOND the
    envelope floor; ``gaps_summary`` = what this baseline LACKS vs the
    envelope union). Drops six prematurely-structured fields whose values
    were never consumed by downstream code.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    agent_id: str = Field(min_length=1)
    excess_summary: str = Field(min_length=1)
    gaps_summary: str = Field(min_length=1)


FairnessVerdict = Literal["pass", "warn", "fail"]


class ProcessFairnessReport(BaseModel):
    """Are all baselines running the same protocol? (same prompt, oracle, budget)"""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: FairnessVerdict
    shared_prompt_template_hash: str = Field(min_length=1)
    shared_oracle_ref: str = Field(min_length=1)
    shared_turn_budget: int = Field(ge=1)
    notes: list[str] = Field(default_factory=list)


class ResourceFairnessReport(BaseModel):
    """Are baseline budget envelopes within an acceptable ratio? (declare, don't clamp)"""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: FairnessVerdict
    cost_ratio_max: float = Field(ge=1.0)
    context_ratio_max: float = Field(ge=1.0)
    output_ratio_max: float = Field(ge=1.0)
    cost_ratio_threshold: float = Field(ge=1.0)
    per_agent_declared: dict[str, dict[str, float | int]]
    notes: list[str] = Field(default_factory=list)


class ProcedureFairnessReport(BaseModel):
    """Same measurement device (Langfuse trace tree, ResultCard schema, KAOS lineage parent)?"""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: FairnessVerdict
    same_trace_parent: bool
    same_result_card_schema_version: str = Field(min_length=1)
    same_kaos_lineage_root: str | None = None
    notes: list[str] = Field(default_factory=list)


class FairnessReport(BaseModel):
    """Pre-Expedition writeup: 3 fairness oracles + balanced envelope (declared, not clamped)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    expedition_id: str = Field(min_length=1)
    process: ProcessFairnessReport
    resource: ResourceFairnessReport
    procedure: ProcedureFairnessReport
    balanced_constraints: BalancedConstraints
    deltas: dict[str, FairnessDelta] = Field(default_factory=dict)
    fairness_verdict: Literal["pass", "warn", "fail"]
    max_capability_drop: int = Field(ge=0)
    advisory_notes: list[str] = Field(default_factory=list)


def stock_manifest(agent_id: str) -> AgentManifest:
    """Built-in manifests for the 3 MVP baselines.

    Conservative defaults — the goal is FAIR baseline, not maxed-out per agent.
    Override via ``adx expedition --manifest <path>`` when running production
    Expeditions with cherry-picked tiers.
    """
    if agent_id == "claude":
        return AgentManifest(
            agent_id="claude",
            model_id="claude-sonnet-4-6",
            context_window_tokens=200_000,
            max_output_tokens=8_000,
            tool_allowlist=["read", "write", "bash", "edit", "grep"],
            latency_budget_sec=120.0,
            cost_ceiling_dollar=1.0,
            special_capabilities=[
                "stream_json",
                "subscription_quota",
                "tool_calls",
                "long_context",
            ],
            auth_mode="subscription",
            notes="Claude Code stream-json over stdio; subscription quota; 1M context tier.",
        )
    if agent_id == "codex":
        return AgentManifest(
            agent_id="codex",
            model_id="gpt-5.5",
            context_window_tokens=128_000,
            max_output_tokens=8_000,
            tool_allowlist=["read", "write", "bash", "edit", "grep"],
            latency_budget_sec=120.0,
            cost_ceiling_dollar=1.0,
            special_capabilities=[
                "json_rpc_lite",
                "subscription_quota",
                "tool_calls",
            ],
            auth_mode="subscription",
            notes="Codex app-server JSON-RPC-lite; subscription quota; cold-fallback via codex exec.",
        )
    if agent_id == "manus":
        return AgentManifest(
            agent_id="manus",
            model_id="manus-1.6-lite",
            context_window_tokens=128_000,
            max_output_tokens=8_000,
            tool_allowlist=["browser", "read", "search"],
            latency_budget_sec=180.0,
            cost_ceiling_dollar=1.0,
            special_capabilities=[
                "browser_dom",
                "api_quota",
                "structured_output",
                "tool_calls",
            ],
            auth_mode="api_key",
            notes="Manus task.create API (sk-mr-* bearer); fallback to Camofox browser then codex-web.",
        )
    raise ValueError(f"no stock manifest for agent_id={agent_id!r}")


__all__ = [
    "AgentManifest",
    "BalancedConstraints",
    "CapabilityLiteral",
    "FairnessDelta",
    "FairnessReport",
    "FairnessVerdict",
    "ProcessFairnessReport",
    "ProcedureFairnessReport",
    "ResourceFairnessReport",
    "stock_manifest",
]
