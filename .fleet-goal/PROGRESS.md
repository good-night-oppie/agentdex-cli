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
- WU-2 DONE + committed:  packages/adx_ladders — LadderAdapter ABC (two-class taxonomy, Receipt tier rules, MeasureResult axes enforcement, pre_run_check) + curated market registry (6 ladders + HF substrate, link-out only). Capsule: evidence/M2/capsules/wu2-ladder-adapter-registry.md.

- WU-3 DONE + committed (84a7c435): arc_agi3 out-of-process adapter — stdio JSON protocol, budget-kill honesty (quality=0, never dropped), D6 receipt branching; 34 tests total, coordinator re-verified.
- WU-4 dispatched (mroute execute): tb2_harbor static-class adapter — HarborProtocol injected, equal-split per-task timeouts, always self_reported receipts w/ per-task summary JSON for M3's decontam gate. Capsule: evidence/M2/capsules/wu4-tb2-harbor-adapter.md.
- Fleet coordination: rpo-addressed A2A handled as parent (rpo idle-done) — ai-scientist's s14 ladder-probe proposal answered DO-NOT-SUBMIT (operator's s14 anti-precedent statement on record); mroute adoption feedback sent (using=yes freq=often).

- WU-4 DONE + committed (be46e1cd): tb2_harbor static-class adapter.
- WU-5 DONE + committed: `adx measure` CLI verb — M2's headline outcome now runs end-to-end (fake engines, hard-fenced receipts); 44 tests, coordinator-verified incl. live invocation.
- Spikes 3 (ToS) + 5 (arXiv) running as a research Workflow (wf_93d1700c-fd5).

- Spikes 2/3/4/5 DONE (evidence/M2/): ToS per-source verdicts; 8/8 arXiv VERIFIED; mixed-direction frontier native (+mean/sum aggregation pinned); fourth adapter = SWE-Bench Pro @ N=10.

- Spike 1 DONE (operator authenticated a fresh account): grant 20 credits, $0.17/3-step toy, per-step transparent billing; `weco start claude` + `weco share` verified; BYO differential unmeasured (supported providers gemini/openai/anthropic only). All five M2 spikes closed.

### What's next

- **M2 audit + review DONE (wf_a973b1de-359): AUDIT_M2_PASS (honesty) + CODE_REVIEW_M2_FAIL (3 CONFIRMED P1 gate bypasses in landed code).** M2 STAYS OPEN. evidence/M2/audit-summary.md.
- WU-6 DONE + committed (2f1060c1): gate-hardening fixes — P1 non-finite budget + non-spec JSON; P1 stdin-deadlock defeats budget kill; P1 process-group kill (grandchildren leak); + gate-integrity P2s (read-only dir, glob confinement, MeasureResult value validation, receipt blank ref). Regression test per bug. Capsule: evidence/M2/capsules/wu6-gate-hardening-fixes.md.
- After WU-6: real-engine integration WUs (arc-agi + Harbor clients, with MEASURED-COST acceptance per P2 finding) → real measured runs filed under evidence/M2/ → re-audit → M3.
- Residual (needs DEFERRED.md rows w/ Until): BYO --api-key differential; PokeAgent organizer ToS ask.

### Any blockers

- M2 blocked from closure until real measured runs exist (real-engine WUs). WU-6 P1 fixes LANDED — all 3 P1s independently re-reproduced-then-confirmed-closed by coordinator; 59 tests, 15 new regressions.

### Any blockers

- None.
