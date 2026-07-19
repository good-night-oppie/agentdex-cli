---
title: "M1 design confirmation (user, verbatim)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

actual_route: coordinator_inline_exception

# M1 evidence item 6 — user confirmation (2026-07-11, verbatim)

> Confirmed — M1 design approved, close M1 and kick off M2. It's sound. The
> two-tier trust (verified = third-party receipt: ARC scorecard / Kaggle
> submission id / PokeAgent server-side rating) + class-differentiated
> kill-gates + PokeAgent auto-degrade-to-static on baseline-skew correctly
> encode the load-bearing rule: the gate scores the REAL objective, not a
> proxy — preserve that through M2's Pareto engine. One guard to keep honest
> in M2: enforce the weco --sources <=10-file limit AND the axes-at-budget
> (quality/cost/wall_clock) partitioning before any run starts, so the
> frontier can never be gamed by a proxy-winner (that's exactly how our s14
> search agent looked great locally then tanked on the real ladder). Proceed
> to M2 — mroute-dispatched engine work.

## Coordinator reading (design consequences)

1. **Load-bearing rule elevated to standing principle:** "the gate scores the
   REAL objective, not a proxy" — carried into M2's evidence requirements and
   every future gate decision (recorded in GOALS.md M2).
2. **Pre-run validation gate is a hard M2 deliverable:** `candidate.py` must
   REJECT before any run starts when (a) the expanded weco-mutable set
   violates the --sources limits (≤10 files, ≤200KB each, ≤500KB total), or
   (b) the run lacks a declared budget / complete axes partition
   (quality, cost_dollar, wall_clock_sec at (ladder, base_model)).
   Anti-precedent: the s14 search agent (proxy-winner locally, tanked on the
   real ladder).
3. **Routing:** M2 implementation dispatched via `mroute execute` — never
   Fable.
