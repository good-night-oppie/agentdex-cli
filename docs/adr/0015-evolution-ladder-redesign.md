---
title: "ADR-0015: Agent Evolution Ladder redesign — Pareto measurement engine + 3-layer RSI loop + knowledge/market site"
status: draft
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
---

# ADR-0015: Agent Evolution Ladder redesign

> **Status: draft — pending M1 design confirmation + audit.**
> Supersedes the invited-user GA product story (user decision 2026-07-11;
> EDITH-M7 fork esc-1335b26251 resolved by supersession). Full design:
> `.fleet-goal/evidence/M1/DESIGN.md`; research: `.fleet-goal/evidence/M1/research/`.

## Context

agentdex pivots from "invited-user battle arena GA" to **the Agent Evolution
Ladder**: an engine that measures a self-evolving agent's Pareto frontier
against chosen task types, a recursive-self-improvement loop composing Weco
and the bene meta-harness, and a website organically combining
agent-evolution.com-style survey knowledge with a competition/ladder/dataset
market. Conceptual frame: Lilian Weng, "Harness Engineering for
Self-Improvement" (2026-07-04) — RSI starts in the harness; the Meta-Harness
paper's output shape ("a collection of harness candidates on the Pareto
frontier") is precisely agentdex's product surface.

## Decisions

### D1 — AgentCandidate is the central noun
Directory + `candidate.yaml` manifest: `entrypoint`, `mutable` globs,
`base_model`, declared `budget`, target `ladders`. Every substrate maps from
it (Harbor import-path wrapper, arcengine shim, poke-env player, weco
`--sources`, mh genome). Resolves the four-incompatible-shapes gap found in
research.

### D2 — 3-layer RSI loop: weco drives, mh gates (user-confirmed)
`adx evolve` wraps **`weco start claude`** (verified: Weco wrapper starts
Claude Code locally, BYO Claude auth default, dashboard = live steering).
Claude Code runs the outer session with an agentdex skill; **`weco run`** is
the optional inner single-metric mutation engine; every candidate goes to the
**bene mh frontier**; **kill-gated promotion** (`autopromote.py` — verified
wired, ACCEPT-only, no back-door) decides leaderboard entry. Data-flow
disclosure (weco uploads sources + eval output; session streams to dashboard)
is mandatory at connect time.

### D3 — bene mh owns the frontier; weco is single-metric; kaos.metaharness rejected
Frontier axes `{quality ↑, cost_dollar ↓, wall_clock_sec ↓}` at a **declared
budget**, partitioned by `(ladder, base_model)` — grounded in RE-Bench's
budget crossover and STOP's base-model gating. Ladder execution is
adapter-owned and **out-of-process** (bene's in-process `exec()` evaluator is
incompatible with hour-scale ladder runs); the frontier store consumes score
dicts only.

### D4 — Two-class ladder taxonomy with class-differentiated kill gates (user directive, verbatim basis)
Live-adversarial (Kaggle, ARC-AGI-3, PokeAgent Challenge): adversarial refresh
is the built-in contamination guard. Static (SWE-Bench Pro, TerminalBench2,
WebArena): held-out/decontamination checks — their datasets sit openly on HF.
HuggingFace is a **substrate**, not a lane. "We land at 6 ladders by merit —
swapping a non-ladder (HF) for a genuine one (pokeagentchallenge) — not by
manufacturing a lane to hit a count."

### D5 — v1 run-adapters: ARC-AGI-3 + Terminal-Bench 2 + PokeAgent (user-confirmed)
Two live-adversarial + one static exercises both gate classes. PokeAgent
diligence PASSED (active; persistent queryable ranking; programmatic
Showdown-API path) and is nearly free on the ADR-0014 poke-env substrate —
team **AgentDex** + bot **adx-bot-1** already provisioned and verified by
authenticated login. WebArena-vs-SWE-Bench-Pro slot 3 decided by M2 footprint
spike. Market page: curated + link-out until the ToS review clears mirroring.

### D6 — Two-tier trust ledger
`verified` = third-party receipt (ARC-AGI-3 scorecard ID, Kaggle submission
ID, PokeAgent server-side rating). `self-reported` = mandatory raw artifacts
(eval logs, transcripts, weco/mh lineage) + spot-replay flag. Storage:
bene.db verdict-engram chain + exported frontier/promotion JSON for the site.

### D7 — Website = knowledge → market → leaderboard, one spine
Absorb the awesome-agent-evolution taxonomy (CC BY 4.0, attribution + repo
link, claim-status labels carried through) as task-type pages; each links its
measuring ladders; each ladder links its frontier partition; each entry links
its verdict chain. Rendered by the repurposed `agentdex_arena` FastAPI app.

### D8 — GA-blocker re-scope (M6)
Auth/DNS/deploy tasks survive re-scoped to serve the new site; Stripe stays
deferred; the old-GA push stops.

## Consequences

**Positive**: measurement moat (auditable frontier, not raw scores); reuses
every proven asset (expedition/verdict machinery, poke-env substrate, bene.db,
arena app); privacy-honest (BYO creds, explicit weco disclosure); promotion
integrity differentiates from raw leaderboards.

**Negative**: dependency on two external services (Weco backend for the driver
UX; ladder operators for receipts); weco single-metric inner loop must be
scalarized against multi-objective axes (mapping contract in adx_frontier);
no fully-local mode in v1 (layering permits adding one later).

## Alternatives considered

Weco-only loop (rejected: loses hash-locked gates + multi-objective frontier);
kaos.metaharness as frontier owner (rejected: vendored, unused, unverified
adapters); hosted multi-tenant execution (deferred: credential custody +
isolation costs); HuggingFace as a sixth ladder lane (rejected: not a ladder —
Open LLM Leaderboard retired; recast as substrate).
