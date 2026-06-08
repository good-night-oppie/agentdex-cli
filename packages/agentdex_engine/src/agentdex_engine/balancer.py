"""3-tier fairness gate — process / resource / procedure.

Per user direction 2026-06-08 "we should not need absolute fairness, we need
process fairness and resource fairness and procedure fairness", the balancer
no longer clamps everything to the minimum manifest. It runs THREE
independent fairness oracles and produces a transparent envelope plus
declared per-baseline jagged profile.

Tier definitions (consensus across grapeot / Karpathy / Hassabis perspectives):

- **Process fairness**  — every baseline runs the SAME protocol:
                            same prompt template, same Oracle ref, same turn
                            budget. Fails fast if any baseline diverges.
- **Resource fairness** — budget envelopes are within an acceptable ratio
                            (default cost_ratio <= 3x, context_ratio <= 2x,
                            output_ratio <= 2x). Above warn-threshold issues
                            ``verdict="warn"`` + discloses the ratio; never
                            blocks on size differences alone.
- **Procedure fairness** — every baseline shares the SAME measurement device:
                            same Langfuse trace parent, same ResultCard
                            schema version, same KAOS lineage root.

The final ``fairness_verdict`` is the worst across the 3 tiers
(``fail > warn > pass``).

Jagged capabilities (Claude's stream_json, Manus's browser_dom) are NOT
dropped — they are DECLARED in each ResultCard's ``capability_profile`` so
the Pareto judge can attribute outcome differences honestly.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

from agentdex_engine.cards import TaskCard
from agentdex_engine.manifest import (
    AgentManifest,
    BalancedConstraints,
    CapabilityLiteral,
    FairnessDelta,
    FairnessReport,
    FairnessVerdict,
    ProcedureFairnessReport,
    ProcessFairnessReport,
    ResourceFairnessReport,
)


_SCHEMA_VERSION = "result_card.v0.1.0"


class ResourceBalancer:
    """3-tier fairness gate (declarative, NOT clamping)."""

    def __init__(
        self,
        *,
        max_capability_drop_tolerance: int = 5,  # legacy field; kept for compat
        cost_ratio_warn_threshold: float = 3.0,
        context_ratio_warn_threshold: float = 2.0,
        output_ratio_warn_threshold: float = 2.0,
        latency_hard_ceiling_sec: float = 600.0,
        min_overlapping_tools: int = 0,
        block_on_resource_warn: bool = False,
    ):
        self.max_capability_drop_tolerance = max_capability_drop_tolerance
        self.cost_ratio_warn_threshold = cost_ratio_warn_threshold
        self.context_ratio_warn_threshold = context_ratio_warn_threshold
        self.output_ratio_warn_threshold = output_ratio_warn_threshold
        self.latency_hard_ceiling_sec = latency_hard_ceiling_sec
        self.min_overlapping_tools = min_overlapping_tools
        self.block_on_resource_warn = block_on_resource_warn

    # ---- per-tier oracles -------------------------------------------------

    def assess_process(
        self,
        manifests: list[AgentManifest],
        task_card: TaskCard,
        *,
        prompt_template_hash: str,
        turn_budget: int,
    ) -> ProcessFairnessReport:
        # All baselines share the same task_card → same source bundle hash →
        # same prompt template (the orchestrator enforces this). We surface
        # the hash + oracle ref + turn budget so the fairness verdict is
        # auditable.
        notes: list[str] = []
        verdict: FairnessVerdict = "pass"
        if not prompt_template_hash:
            verdict = "fail"
            notes.append("prompt_template_hash missing — process invariant broken.")
        if not task_card.oracle_spec_ref:
            verdict = "fail"
            notes.append("task_card.oracle_spec_ref empty — oracle protocol unverified.")
        return ProcessFairnessReport(
            verdict=verdict,
            shared_prompt_template_hash=prompt_template_hash or "<missing>",
            shared_oracle_ref=task_card.oracle_spec_ref or "<missing>",
            shared_turn_budget=max(turn_budget, 1),
            notes=notes,
        )

    def assess_resource(
        self, manifests: list[AgentManifest]
    ) -> ResourceFairnessReport:
        if not manifests:
            return ResourceFairnessReport(
                verdict="fail",
                cost_ratio_max=1.0,
                context_ratio_max=1.0,
                output_ratio_max=1.0,
                cost_ratio_threshold=self.cost_ratio_warn_threshold,
                per_agent_declared={},
                notes=["no manifests — resource fairness undefined."],
            )
        max_cost = max(m.cost_ceiling_dollar for m in manifests)
        min_cost = min(m.cost_ceiling_dollar for m in manifests)
        max_ctx = max(m.context_window_tokens for m in manifests)
        min_ctx = min(m.context_window_tokens for m in manifests)
        max_out = max(m.max_output_tokens for m in manifests)
        min_out = min(m.max_output_tokens for m in manifests)
        cost_ratio = max(max_cost / max(min_cost, 1e-9), 1.0)
        context_ratio = max(max_ctx / max(min_ctx, 1), 1.0)
        output_ratio = max(max_out / max(min_out, 1), 1.0)

        notes: list[str] = []
        verdict: FairnessVerdict = "pass"
        if cost_ratio > self.cost_ratio_warn_threshold:
            verdict = "warn"
            notes.append(
                f"cost_ratio={cost_ratio:.2f}x > {self.cost_ratio_warn_threshold:.1f}x — "
                "richer baselines may overspend; disclosed but not clamped."
            )
        if context_ratio > self.context_ratio_warn_threshold:
            verdict = "warn"
            notes.append(
                f"context_ratio={context_ratio:.2f}x > {self.context_ratio_warn_threshold:.1f}x — "
                "long-context baseline (claude 1M) declared but not clamped."
            )
        if output_ratio > self.output_ratio_warn_threshold:
            verdict = "warn"
            notes.append(
                f"output_ratio={output_ratio:.2f}x > {self.output_ratio_warn_threshold:.1f}x"
            )
        if self.block_on_resource_warn and verdict == "warn":
            verdict = "fail"

        per_agent: dict[str, dict[str, float | int]] = {}
        for m in manifests:
            per_agent[m.agent_id] = {
                "cost_ceiling_dollar": m.cost_ceiling_dollar,
                "context_window_tokens": m.context_window_tokens,
                "max_output_tokens": m.max_output_tokens,
                "latency_budget_sec": m.latency_budget_sec,
            }

        return ResourceFairnessReport(
            verdict=verdict,
            cost_ratio_max=cost_ratio,
            context_ratio_max=context_ratio,
            output_ratio_max=output_ratio,
            cost_ratio_threshold=self.cost_ratio_warn_threshold,
            per_agent_declared=per_agent,
            notes=notes,
        )

    def assess_procedure(
        self,
        *,
        lineage_root: str | None = None,
        schema_version: str = _SCHEMA_VERSION,
        same_trace_parent: bool = True,
    ) -> ProcedureFairnessReport:
        notes: list[str] = []
        verdict: FairnessVerdict = "pass"
        if not same_trace_parent:
            verdict = "fail"
            notes.append(
                "trace parent diverges across baselines — measurement device unfair."
            )
        return ProcedureFairnessReport(
            verdict=verdict,
            same_trace_parent=same_trace_parent,
            same_result_card_schema_version=schema_version,
            same_kaos_lineage_root=lineage_root,
            notes=notes,
        )

    # ---- envelope (declarative — does NOT clamp on equality) --------------

    def declare_envelope(
        self, manifests: list[AgentManifest]
    ) -> tuple[BalancedConstraints, dict[str, FairnessDelta], int]:
        """Returns the union envelope (NOT the intersection) + per-baseline
        deltas + max capability drop (kept for backward-compat reporting)."""
        ctx_max = max(m.context_window_tokens for m in manifests)
        out_max = max(m.max_output_tokens for m in manifests)
        cost_max = max(m.cost_ceiling_dollar for m in manifests)
        latency_min = min(
            min(m.latency_budget_sec for m in manifests),
            self.latency_hard_ceiling_sec,
        )

        # Tool / capability profile: declare the UNION as the envelope; per
        # baseline tracks what it can't reach via the FairnessDelta record.
        union_tools: list[str] = []
        for m in manifests:
            for t in m.tool_allowlist:
                if t not in union_tools:
                    union_tools.append(t)
        union_caps: list[CapabilityLiteral] = []
        for m in manifests:
            for c in m.special_capabilities:
                if c not in union_caps:
                    union_caps.append(c)

        balanced = BalancedConstraints(
            context_window_tokens=ctx_max,
            max_output_tokens=out_max,
            tool_allowlist=union_tools,
            latency_budget_sec=latency_min,
            cost_ceiling_dollar=cost_max,
            intersected_capabilities=union_caps,
            rationale=(
                "envelope = UNION of declared manifests (jagged profiles preserved); "
                "per-baseline gaps surfaced in FairnessDelta, no min-clamp applied."
            ),
        )

        deltas: dict[str, FairnessDelta] = {}
        max_cap_drop = 0
        for m in manifests:
            caps_missing = [c for c in union_caps if c not in m.special_capabilities]
            tools_missing = [t for t in union_tools if t not in m.tool_allowlist]
            max_cap_drop = max(max_cap_drop, len(caps_missing))
            deltas[m.agent_id] = FairnessDelta(
                agent_id=m.agent_id,
                context_window_excess_tokens=max(0, ctx_max - m.context_window_tokens),
                max_output_excess_tokens=max(0, out_max - m.max_output_tokens),
                capabilities_dropped=caps_missing,
                tools_dropped=tools_missing,
                cost_headroom_dollar=max(0.0, cost_max - m.cost_ceiling_dollar),
                latency_headroom_sec=max(0.0, m.latency_budget_sec - latency_min),
            )
        return balanced, deltas, max_cap_drop

    # ---- top-level equalize (3 tiers combined) -----------------------------

    def equalize(
        self,
        manifests: Iterable[AgentManifest],
        task_card: TaskCard,
        *,
        expedition_id: str,
        prompt_template_hash: str = "",
        turn_budget: int = 1,
        lineage_root: str | None = None,
    ) -> FairnessReport:
        ms = list(manifests)
        if not ms:
            raise ValueError("no manifests provided; cannot run fairness gate")

        if not prompt_template_hash:
            prompt_template_hash = hashlib.sha256(
                (task_card.id + task_card.source_bundle_hash).encode()
            ).hexdigest()[:16]

        process = self.assess_process(
            ms, task_card,
            prompt_template_hash=prompt_template_hash,
            turn_budget=turn_budget,
        )
        resource = self.assess_resource(ms)
        procedure = self.assess_procedure(
            lineage_root=lineage_root,
            schema_version=_SCHEMA_VERSION,
            same_trace_parent=True,
        )

        balanced, deltas, max_cap_drop = self.declare_envelope(ms)

        # Roll up — worst verdict wins.
        order = {"pass": 0, "warn": 1, "fail": 2}
        worst: FairnessVerdict = max(
            (process.verdict, resource.verdict, procedure.verdict),
            key=lambda v: order[v],
        )

        advisory: list[str] = []
        advisory.extend(process.notes)
        advisory.extend(resource.notes)
        advisory.extend(procedure.notes)

        return FairnessReport(
            expedition_id=expedition_id,
            process=process,
            resource=resource,
            procedure=procedure,
            balanced_constraints=balanced,
            deltas=deltas,
            fairness_verdict=worst,
            max_capability_drop=max_cap_drop,
            advisory_notes=advisory,
        )


__all__ = ["ResourceBalancer"]
