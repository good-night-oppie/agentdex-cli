---
title: "agentdex redesign — architecture design (M1)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

actual_route: coordinator_inline_exception (synthesis over 6-lane research + gap critic, wf_5e0dbcd5-c53)

# Architecture Design: agentdex — the Agent Evolution Ladder

## Requirements Summary

- **Purpose**: measure a self-evolving agent's **Pareto frontier against a
  chosen task type**, drive its **recursive self-improvement** with a
  weco-driven Claude Code loop gated by the bene meta-harness, and publish
  both knowledge and results on a website that organically combines
  agent-evolution.com-style survey content with a **competition/ladder/dataset
  market**.
- **Scale**: single-user local execution (BYO creds) + one public website;
  no hosted multi-tenant compute in v1.
- **Integrations**: Weco (`weco start claude`, `weco run`), bene meta-harness
  (frontier + kill gates), ladders (ARC-AGI-3, Terminal-Bench 2, PokeAgent
  Challenge live; Kaggle/SWE-Bench Pro/WebArena curated), HuggingFace as
  dataset substrate, Langfuse traces (existing).
- **Supersession**: replaces the invited-user GA supergoal; the 7 blocked GA
  tasks are re-scoped in M6.

## Recommended Architecture

**Style**: Modular monolith on the existing uv workspace (9 packages today,
verified — README says 7, doc drift), extended with three new packages and one
repurposed app. No microservices: one operator, one box, artifact-file
contracts between layers (Weng Pattern 2: file system as persistent memory).

**Rationale**: every load-bearing substrate already exists in-tree or on-host
(expedition/Pareto-verdict machinery, poke-env battle substrate from ADR-0014,
bene.db meta-harness with verified gated auto-promotion, arena FastAPI app).
The redesign is a re-composition around a new central noun — the
**AgentCandidate** — not a rebuild.

## The core loop (3-layer, user-confirmed)

```
┌──────────────────────────────────────────────────────────────────────┐
│ OUTER — driver session (user's machine, BYO Claude auth)             │
│   adx evolve → `weco start claude` → Claude Code + agentdex skill    │
│   Weco dashboard = live steering surface (read along, message back)  │
│                                                                      │
│   ┌── MIDDLE — measurement (adx measure)                             │
│   │   ladder adapters run the AgentCandidate out-of-process,         │
│   │   emit score dicts {quality, cost_dollar, wall_clock_sec}        │
│   │   at a DECLARED BUDGET                                           │
│   │                                                                  │
│   ┌── INNER — focused mutation (optional per iteration)              │
│   │   `weco run` — server-side AIDE tree search over the             │
│   │   candidate's mutable-file globs, single scalar metric           │
│   │   (disclosure: sources + eval output upload to Weco backend)     │
│   │                                                                  │
│   └─→ mh_submit_candidate → bene mh frontier (multi-objective,       │
│       persistent, partitioned by (ladder, base_model))               │
│       → EXPLICIT bridge in adx_frontier/mh_bridge.py                 │
│         (genome_from_candidate → registered gate → promote() on      │
│         ACCEPT) → agentdex ledger/leaderboard                        │
└──────────────────────────────────────────────────────────────────────┘
```

**Promotion-integrity qualifier (P1 review finding):** `autopromote.py`'s
ACCEPT-only kill-gated promotion is verified wired on bene's **autonomous**
search path only; the **collaborative MCP path used above never bridges or
auto-promotes** (it writes archive files directly). The bridge in
`mh_bridge.py` is therefore a REQUIRED component, not an optimization, and
M3's evidence must show a candidate promoted through an ACCEPT gate via the
collaborative path. GAP-10 (SKILL.md "not wired" vs working-tree code):
single squashed import commit — working-tree `autopromote.py` is canonical,
SKILL.md claim stale.

Division of labor (GAP-2 resolution): **bene mh owns the frontier and
promotion integrity** (only verified persistent multi-objective substrate;
hash-locked kill gates; gated auto-promote verified wired in
`bene/kernel/evolve/autopromote.py` — ACCEPT-only, no back-door). **Weco owns
inner-loop code mutation** (single-metric tree search) and the **driver
wrapper + steering dashboard**. **agentdex owns measurement, the ledger, the
leaderboard, and the website.** kaos.metaharness (vendored, unused) is
rejected. Ladder execution is **adapter-owned and out-of-process** (GAP-8) —
never inside bene's in-process evaluator.

## AgentCandidate — the central noun (GAP-3 resolution)

A directory + `candidate.yaml` manifest:

```yaml
name: my-agent
entrypoint: "python -m my_agent"        # how to run it
mutable: ["src/**/*.py", "prompts/*"]   # weco --sources + mh genome scope
base_model: claude-sonnet-5             # frontier partition key (STOP)
budget: {usd: 5.00, wall_clock_min: 60} # declared budget (RE-Bench crossover)
ladders: [tb2, arc-agi-3, pokeagent-gen1ou]
```

Validation rule (weco hard limits, first-class in `adx_frontier/candidate.py`):
the expanded `mutable` set passed to `weco run --sources` must be **≤10 files,
≤200KB each, ≤500KB total** — broad globs like `src/**/*.py` fail validation
with a "narrow your weco-mutable subset" error before any run starts; the mh
genome may still cover the full set.

Each adapter maps it to its native shape: TB2/Harbor `--agent-import-path`
wrapper; ARC-AGI-3 arcengine SDK shim; PokeAgent poke-env player authing as
the team bot (`adx-bot-1` + agent password); weco `--sources` = the mutable
globs; bene mh genome = manifest + mutable files.

## Frontier + ledger data model (GAP-4/5 resolution)

- **Axes**: `{quality: ladder-native score ↑, cost_dollar ↓, wall_clock_sec ↓}`
  at a declared budget. Frontier partitioned by `(ladder, base_model)` —
  justified by STOP (base model gates whether loops help) and RE-Bench
  (score is a function of budget).
- **Two-tier trust**: `verified` entries carry a third-party receipt
  (ARC-AGI-3 official scorecard ID, Kaggle submission ID, **PokeAgent ladder
  rating — server-side computed, inherently verified**); `self-reported`
  entries require raw artifacts (eval logs, transcripts, weco/mh lineage
  JSON) + a spot-replay flag.
- **Storage**: bene.db engrams (candidate lineage, verdict chain) + exported
  `frontier.json`/`promotion.json` the website renders. One portable SQLite
  file audits a leaderboard entry end-to-end.

## Ladder taxonomy + gate semantics (user requirement 5)

| Class | Ladders | Kill-gate guard |
|---|---|---|
| Live-adversarial | Kaggle, ARC-AGI-3, **PokeAgent Challenge** | adversarial refresh is the built-in contamination guard |
| Static leaderboard | SWE-Bench Pro, TerminalBench2, WebArena | held-out / decontamination checks (datasets sit openly on HF) |
| Substrate (not a lane) | HuggingFace | — datasets/distribution/model-hosting powering the above |

v1 run-adapters (user-confirmed): **ARC-AGI-3 + TB2 + PokeAgent** — both gate
classes exercised; PokeAgent nearly free on the ADR-0014 poke-env substrate
with team AgentDex + bot adx-bot-1 already provisioned (diligence PASS, see
`research/pokeagent-diligence.md`). Market page: curated metadata + link-out
(no leaderboard mirroring until the ToS session clears it — GAP-6 fallback).

## Module Structure (uv workspace deltas)

```
packages/
├── adx_ladders/        # NEW — LadderAdapter ABC + registry
│   ├── adapters/{arc_agi3, tb2_harbor, pokeagent}.py   # v1 executable
│   ├── market/registry.yaml       # all 6 + HF substrate, curated, link-out
│   └── verify.py                  # receipt capture (scorecard/submission/rating)
├── adx_frontier/       # NEW — measurement ledger
│   ├── candidate.py               # AgentCandidate manifest load/validate
│   ├── mh_bridge.py               # mh_submit_candidate / frontier / autopromote
│   ├── gates.py                   # class-differentiated kill-gate policies
│   └── export.py                  # frontier.json / promotion.json for the site
├── adx_evolve/         # NEW — the RSI loop
│   ├── driver.py                  # wraps `weco start claude`; session mgmt
│   ├── skill/                     # agentdex skill installed into the session
│   └── weco_inner.py              # `weco run` invocation + result ingest
├── agentdex_engine/    # EXTEND — Pareto verdict generalized to axes-at-budget;
│                       #   Evolution Card mutation seeds feed mh rationale
├── agentdex_arena/     # REPURPOSE — FastAPI app → website:
│                       #   /knowledge (taxonomy, CC BY attribution, claim-status
│                       #   labels carried through), /market, /leaderboard
├── adx_bridges/        # KEEP — subscription-CLI bridges
├── adx_showdown/       # KEEP (ADR-0014 poke-env path; shared w/ pokeagent adapter)
├── agentdex_cli/       # EXTEND — new verbs (below)
├── agentdex_observe/   # KEEP — Langfuse traces
├── agentdex_plugin/    # RETIRE — Hermes entry-points integration superseded
│                       #   by the weco→Claude Code driver; drops hermes-agent dep
├── helios_client/      # RETIRE — never wired; keep the CheckpointStore Protocol
└── kaos/               # KEEP as substrate; kaos.metaharness NOT selected
```

## CLI surface

```
adx measure --agent <dir> --ladder <id> [--budget usd=5,min=60]  # Pareto engine MVP
adx evolve  --agent <dir> --ladder <id> [--steps N] [--weco-inner]
adx ladders {list,info,verify-receipt}
adx ledger  {show,push,export}
adx site    {build,serve}
```

## Module Boundaries

| Module | Responsibility | Dependencies |
|---|---|---|
| adx_ladders | execute candidate on a ladder, emit score dict + receipt | candidate manifest; ladder SDKs (out-of-process) |
| adx_frontier | frontier, gates, promotion, export | bene mh (MCP/lib), adx_ladders scores |
| adx_evolve | RSI driver session + inner weco loop | weco CLI, adx_ladders, adx_frontier |
| agentdex_engine | axes-at-budget verdicts, Evolution Cards | adx_frontier |
| agentdex_arena | website (knowledge/market/leaderboard) | adx_frontier exports, adx_ladders registry |

## Data flow disclosure (must appear in docs + connect-time prompt)

`weco start claude` streams the session conversation to the Weco dashboard;
`weco run` uploads mutable source files + eval output to Weco's backend.
Default remains local Claude auth (BYO); `--billing weco` is opt-in. A
fully-local mh-only mode is NOT in v1 (user chose 3-layer) but nothing in the
layering precludes adding it later.

## Website composition (the "organic combination")

Taxonomy categories (absorbed from awesome-agent-evolution, CC BY 4.0
attribution "Self Evolve / Awesome Self-Evolving AI Agents, aha team" + repo
link, `[INFERRED]`/claim-status labels carried through) map to **task types**;
each task type page links the ladders that measure it; each ladder page links
the leaderboard partition `(ladder, base_model)` rendered from frontier
exports; each leaderboard entry links its verdict chain (verified receipt or
self-reported artifacts). Knowledge → market → leaderboard is one navigation
spine, not three sites.

## Open items carried to M2 (decided-by-default, spike-gated)

1. Weco spike: credit economics with BYO `--api-key` + retention policy +
   empirical `weco start claude` verb check (`--help`, one bridged toy
   session) — gates the "free on your own subscriptions" copy and the D2
   driver mechanism (the verb post-dates the docs seed; snapshot captured in
   `research/weco-start-claude-snapshot.md`).
2. WebArena vs SWE-Bench Pro footprint spike → the FOURTH adapter slot
   (v1 ships three: ARC-AGI-3, TB2, PokeAgent).
3. ToS browser session: benchmark-leaderboard mirroring per ladder AND Weco's
   own ToS on third-party display of exported run/lineage data + share-link
   embedding (D6 self-reported tier ingests weco lineage JSON; M5 renders it
   publicly).
4. bene `Benchmark.score()` cost/latency axes spike (free-form floats say yes).
5. arXiv ID verification pass for citations (2603.28052, 2604.01658,
   2603.15563 PokeAgent, Weng reference set).

## Next Steps

1. User confirms this design (M1 evidence item 6).
2. ADR-0015 records the decisions (draft alongside this doc).
3. M1 audit + review (fresh thread), then M2 implementation begins.
