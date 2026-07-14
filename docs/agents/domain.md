---
title: "Agent skills — domain doc consumer rules"
status: active
owner: "@EdwardTang"
created: 2026-07-14
updated: 2026-07-14
type: reference
scope: docs/agents
layer: cross-cutting
cross_cutting: true
---

# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

**Layout: single-context.** One `CONTEXT.md` + `docs/adr/` at the repo root.

## Before exploring, read these

- **`CLAUDE.md`** at the repo root — **the load-bearing one here.** It carries the
  architectural commitments (why KAOS is vendored, why helios stays external, the
  bridge contract, membership gate call order, badge mint call order) **and the
  glossary** (Three Cards, Oracle layer, Pareto verdict, Mutation seed). Treat its
  `## Glossary` section as this repo's `CONTEXT.md` until a real one exists.
- **`CONTEXT.md`** at the repo root — does not exist yet. `/domain-modeling` will
  create it lazily when terms actually need resolving. Until then, `CLAUDE.md`
  §Glossary is the vocabulary of record.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. All ADRs
  here are **system-wide and root-level** (currently 0009–0015). There are no
  package-scoped ADRs.
- **`AGENTS.md`** — the modular index. Points at review digests and the
  `pr-cascade-breaker` FSM.

If any of these files don't exist, **proceed silently**. Don't flag their absence;
don't suggest creating them upfront. The `/domain-modeling` skill (reached via
`/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when
terms or decisions actually get resolved.

## File structure

This repo is a **uv workspace** with 11 members under `packages/*` — so it is
structurally a monorepo, but its domain docs are deliberately **single-context**:

```
/
├── CLAUDE.md                          ← doctrine + glossary (de-facto CONTEXT.md)
├── AGENTS.md                          ← modular index
├── CONTEXT.md                         ← (not yet created; /domain-modeling will)
├── docs/adr/                          ← ALL decisions, system-wide
│   ├── 0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md
│   ├── 0011-gtm-a-membership-primitive-and-paid-feature-positioning.md
│   └── 0015-evolution-ladder-redesign.md
└── packages/
    ├── agentdex_cli/     agentdex_engine/    agentdex_plugin/
    ├── adx_bridges/      adx_showdown/       adx_frontier/
    ├── adx_ladders/      agentdex_arena/     agentdex_observe/
    ├── helios_client/    kaos/               ← vendored subtree
```

**Why single-context despite 11 packages:** the ADR cascade documented in
`CLAUDE.md` is root-centric by design — ADR-0009 is the unifying meta-ADR that the
package boundaries *derive from*, not the other way round. Splitting decisions into
`packages/<pkg>/docs/adr/` would fragment that cascade. If a package ever grows
decisions that genuinely don't leave its boundary, the escape hatch is: add a root
`CONTEXT-MAP.md`, add `packages/<pkg>/CONTEXT.md`, and put package-scoped ADRs in
`packages/<pkg>/docs/adr/`. Nothing populates that today — don't pre-build it.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a
hypothesis, a test name), use the term as defined in `CLAUDE.md` §Glossary. Don't
drift to synonyms the glossary explicitly avoids.

Load-bearing terms with non-obvious meanings — get these right:

- **Three Cards** — TaskCard / ResultCard / EvolutionCard. Not "the cards", not "records".
- **Pareto verdict** — `winner` | `no_clear_winner`. Not "the result", not "the score".
- **Mutation seed** — a pydantic `Seed` with `seed_provenance ∈ {structural, learned}`.
- **Async co-opetition (合作竞争)** — baselines run **sequentially**, judged after the
  fact. Never call it a "race", a "battle", or "real-time" — that framing is
  explicitly retracted in `CLAUDE.md` (ADR-0009 §Amendment-2026-06-08).

If the concept you need isn't in the glossary yet, that's a signal — either you're
inventing language the project doesn't use (reconsider) or there's a real gap (note
it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than
silently overriding:

> _Contradicts ADR-0011 (membership primitive) — but worth reopening because…_

Two conflicts worth knowing about before you propose anything:

- **Anti-pay-to-rank (ADR-0011 §3a–d)** is encoded as the *absence* of
  `@require_membership` on free routes. A proposal that gates `/ladder`, or that
  rate-limits free users on any `recompute_ladder` path, contradicts it — even if
  no decorator is added.
- **The sync wrapper is the M5 load-bearing path** (`CLAUDE.md` §Async co-opetition,
  doctrine note 2026-06-09). Calling the async primitives "the source of truth" is a
  known anchor-drift failure. Don't repeat it.
