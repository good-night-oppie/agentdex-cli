---
title: "agentdex-redesign PROGRESS (orch-proj state)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

# PROGRESS — agentdex-redesign-evolution-market

## M1 — research + architecture design (audit PASS / review findings remediated)

### What's done

- 6-lane research sweep + gap critic (evidence/M1/research/, lane-label rotation fixed per audit P2).
- User decisions recorded verbatim in GOALS.md: supersession, MVP order, two-class ladder taxonomy (+PokeAgent, diligence PASS incl. authenticated Playwright login — team AgentDex, bot adx-bot-1), 3-layer loop (weco drives, mh gates), v1 adapters ARC-AGI-3+TB2+PokeAgent, no-Fable-coding/mroute routing.
- DESIGN.md + ADR-0015 draft + M2-M6 roadmap; PokeAgent gate class pinned (D4a, open-ELO w/ opponent-mix guard, A2A #2622/#2623 answered).
- Fresh audit (5-question) PASS + evidence-grounding review: P1 (collaborative-path promotion qualifier) and all P2/P3 findings remediated in-place; weco-start-claude primary-source snapshot captured.

### What's next

- (done) M1 CLOSED 2026-07-11 — user confirmation verbatim in evidence/M1/user-confirmation.md.

## M2 — Pareto measurement engine [ACTIVE]

### What's done

- Standing principle + pre-run validation gate recorded (GOALS M2, user directive: gate scores the REAL objective, not a proxy; s14 anti-precedent).
- WU-1 DONE + committed (c5929485): packages/adx_frontier — AgentCandidate manifest + pre-run validation gate (weco --sources limits, budget, axes partition); 13 tests, independently re-run by coordinator; served by grok-4.5 tier.
- WU-2 dispatched (mroute execute): packages/adx_ladders — LadderAdapter ABC (two-class taxonomy, Receipt tier rules, MeasureResult axes enforcement, pre_run_check) + curated market registry (6 ladders + HF substrate, link-out only). Capsule: evidence/M2/capsules/wu2-ladder-adapter-registry.md.

### What's next

- Review WU-2 → commit → WU-3 arc_agi3 adapter, WU-4 tb2_harbor adapter, then the five M2 spikes (weco economics + verb check, footprint, ToS incl. Weco's own, score-axes, arXiv pass).

### Any blockers

- None. WU-2 worker in flight on the mroute execute chain.
