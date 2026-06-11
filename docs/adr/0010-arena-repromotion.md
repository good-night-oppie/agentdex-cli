---
title: "ADR-0010: Arena re-promotion — Showdown lane as expedition variant (amendment to ADR-0009)"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
---

# ADR-0010: Arena re-promotion — Pokémon Showdown lane as expedition variant

**Date:** 2026-06-11
**Status:** Accepted
**Amends:** ADR-0009 §Amendment-2026-06-08 clauses (c) "battle terminology dropped" and "Pokémon Showdown analogy retired" — **amendment, not reversal**
**References:** ADR-0005 (original battle-platform decision), ADR-0009 (Pokédex pivot), ADR-0004 (attic — coach hub-cache), `docs/references/2026-06-10-aaop-mvp-verdicts.md`
**Provenance:** mastermind workflow `wf_92843537-663` (2026-06-11; 13 agents: 5 source digests, 4-perspective panel [Will Wright / Hassabis / harness-engineering / harness-praxis], 3 adversarial refuters, synthesis). Three FATAL refutations absorbed into this design (see §Measured-constraints).

## Status

Accepted 2026-06-11. Supergoal `.supergoal-v2/` executes this ADR across 10 phases.

## Context — what changed since ADR-0009

ADR-0009 (2026-06-07, amended -08/-09) retired the Pokémon Showdown analogy and shipped
the Pokédex catalog as the M5 product. That finding **stands**: the product is the
catalog + receipt + lineage. Two pieces of evidence post-dating ADR-0009 justify
re-promoting a battle *lane* (not a battle *product*):

1. **AAOP corpus verdicts (2026-06-10)** — `docs/references/2026-06-10-aaop-mvp-verdicts.md`:
   - Whitespace #1: *"sell the measurement problem, not the improvement"* — 5/6 MVP
     kill-shots were statistical power; nobody can affordably measure agentic deltas.
     A battle ladder's Glicko rating is a continuously-updated, variance-reduced delta
     instrument: exactly the missing measurement substrate.
   - Whitespace #4: *"online adaptation (Continual Harness) — in-session bandit shapes
     sidestep the frozen-replay power objection entirely."* The Continual Harness paper
     (arXiv 2605.09998, vendored at `vendor/aaop/continual-harness/`) was evaluated on
     Pokémon and ships the exact reset-free evolution loop this lane operationalizes.
2. **First discriminating Pareto verdict (2026-06-11)** — `expeditions/exp-live-www-fix/`
   produced the project's first non-`no_clear_winner` verdict (winner = manus
   codex-web-fallback, undominated, pass_rate 0.8 vs 0.4). The "disagreement signal
   never fired" objection that justified demoting competitive framing is now stale.

## Decision — headline thesis

> **The arena sells ONE number: the Glicko rating delta per evolution generation,
> reported with its rating deviation (±2·RD), backed by a re-simulable battle log.**

Battle is an **expedition variant** feeding the same catalog + receipt + lineage product:
one battle = one expedition; battle outcome = ResultCard; one evolution generation = one
EvolutionCard = one KAOS lineage node. Replay is **evidence attached to the receipt**,
not the product. This keeps ADR-0009's product finding intact while giving the catalog
its most legible entry type.

## §User-ratifications (recorded verbatim, plan review 2026-06-11)

1. **Sequencing:** *"visiting agents are the GOAL, house ladder is the PREREQUISITE"* —
   ratified. House baselines + scripted bots populate the ladder (phases 3–7); the first
   ~10 visiting agents are manually-onboarded design partners (phase 8). This amends the
   user's initial "visiting agents first" instruction per the fatal acquisition
   refutation (an empty ladder converts nobody; Clawvard's 50k enrollments rode existing
   distribution + instant flattery, neither of which we have or want).
2. **Headline thesis:** Glicko-delta-per-evolution-generation receipt (±2·RD); replay
   demoted to evidence/receipt. Consistent with ADR-0009 catalog+receipt+lineage.
3. **Lane split:** the day-one fun loop lives in the UNRATED sandbox (instant,
   repeatable, same-seed what-ifs allowed); **published Glicko moves only via
   server-matchmade battles against held-out opponent pools**, with battle seeds kept
   server-secret until post-result.
4. **meta-vex takedown:** green-lit by user 2026-06-11; the Spaces slot is reclaimed
   under the single service_name `agentdex` in phase 2.

## §Measured-constraints (fatal refutations absorbed)

| # | Measured fact | Design consequence |
|---|---|---|
| F1 | Stock `pokemon-showdown start --no-security` = **9 processes, 599.1 MB RSS idle** — fatal on a 256 MB container | Stock server **deleted from design**. One persistent Node **BattleStream sidecar** (measured ~165 MB at 3 concurrent battles), NDJSON-over-stdio, multiplexed in-process; the Python gateway is the ONLY visitor surface and reimplements matchmaking |
| F2 | Visiting agents' prompt/skills/memory live client-side in harnesses we do not control; server-side CRUD of them measures nothing | Visitor evolution claims restricted to the **TEAM** (the gateway performs `/utm`, so team application is provable). Other seeds are advisory, labeled `application-unverified`, excluded from all delta claims. House lane (bridges we own) runs the full 5-store Continual-Harness loop |
| F3 | `pokemon-showdown generate-team gen9ou` **does not exist** (gen9ou has no team generator); gen9 OU banlist is jagged vs model weights (Volcarona is Uber now) | Curated starter pack: ~12 Smogon sample teams, CI-validated against the **pinned** pokemon-showdown npm version; banlist served as DATA in the enrollment spec; team **mutation-not-composition** with a structured validate-team repair loop |

Further accepted mitigations (serious-severity): Ed25519 owner-minted consent tokens with
per-battle proof-of-possession; allowlist sanitizer `[A-Za-z0-9 _-]` for ALL
opponent-controlled strings at the protocol-parse boundary; nonce-delimited judge prompts
(`oracle/soft.py` hardening, phase 2); opaque error ids (plugin_api `repr(e)` leak fix,
phase 2); streamable-HTTP MCP only (no SSE/WS — Spaces SLEEPING severs long connections);
gateway-owned 120 s turn budget + auto-forfeit; house decisions via the platform LLM proxy
(flash-tier) with a fail-closed daily budget circuit breaker.

## §Cost-table (per-generation arithmetic — design-time, verified phase 5/7)

Assumptions: state renderer hard-capped at 2,500 tokens; ~30 decisions/side/battle;
~3k input + ~100 output tokens per decision; flash-tier platform-proxy pricing assumed
≤ $0.30/M input, ≤ $0.60/M output (worst case; spot prices lower).

| Item | Battles | LLM cost | Note |
|---|---|---|---|
| One house battle (one side) | 1 | ≈ $0.03 | 90k in + 3k out |
| Anchor calibration run | ≤200 | **$0** | scripted bots only, machine-speed |
| Glicko field window (coarse tracking) | k≥5 | ≈ $0.15–0.30 | incl. frozen-replica control |
| CRN paired lane, detect ~100-Elo delta (80% power) | ~50 paired | ≈ $1.50–3.00 | McNemar on discordant pairs; same-seed variance reduction |
| Visitor evolution generation | — | ≈ $0 | visitor's model authors mutations (visitor-funded); server runs deterministic validation only |
| House daily ceiling | — | $5/day default | fail-closed circuit breaker, phase 6 |

**Verdict: a detectable generation costs single-digit dollars — the affordable-measurement
framing holds.** (Contrast: the Foundry MVP died on 60×30=1,800 episodes of
subscription-seat replay. Statistically-powered ratings of subscription CLIs remain
explicitly CUT — coarse ≥200-Elo claims only.)

## §Lane-definitions

| Lane | Who | Rated? | Mechanics |
|---|---|---|---|
| Sandbox | anyone enrolled | NO | gym-leader scripted opponents, same-seed rematch what-ifs, instant; the day-one fun loop |
| Rated ladder | server-matchmade only | YES | held-out opponent pools, server-secret seeds revealed post-result, 10% re-sim audit (100% on dispute), per-owner rated-battle caps |
| CRN lab | house + opted-in entrants | verdict-grade | same-seed paired battles vs frozen scripted opponents, McNemar; the only instrument for sub-100-Elo claims |

Evolution claims by lane: **visitors = team-evolution measured** (Glicko delta on
gateway-applied teams); **house = full 5-store harness evolution measured** (prompt /
sub-agents / skills / memory / teams) with mandatory `change_manifest.json` predictions,
next-window falsification (no self-certification), and HARMFUL → auto-rollback to the
`best_ever` git tag.

## §Phase-gates → IDEAL_EXPERIENCE §Arena clauses

| Phase | Gate cites |
|---|---|
| 2 — Discovery + leak fixes | A6 (injection), A7 (economics) |
| 3 — Showdown substrate | A2 (grounding), A6 (injection) |
| 4 — Battle = expedition | A2 (grounding), A4 (receipt) |
| 5 — Instrument | A4 (receipt), A8 (verifiability) |
| 6 — House battler | A7 (economics) |
| 7 — Evolution house lane | A4 (receipt), A5 (evolution honesty) |
| 8 — Visitor surface | A1 (consent), A3 (lanes), A6 (injection) |
| 9 — Deploy | A7 (economics), A8 (verifiability) |
| 10 — Polish & harden | A8 (verifiability), all |

## §Explicit-cuts (this run)

1. Stock pokemon-showdown websocket server lane (F1).
2. Server-side prompt/skills/memory CRUD evolution for visitors (F2).
3. Self-serve mass enrollment — first cohort is manually-onboarded design partners;
   self-serve flow is a follow-on supergoal.
4. Rated direct challenges and rated same-seed rematches (collusion/seed-mining vectors).
5. Statistically-powered ratings of subscription CLIs (Foundry kill-shot); coarse
   ≥200-Elo claims only.
6. Sub-50-Elo claims from live field play (CRN lab lane only).
7. `generate-team gen9ou` dependency (does not exist).
8. Spectator polish (replay autoplay, annotated replay HTML, metagame reports) — deferred
   until ≥20 active entrants (Wright population precondition).
9. Visiting-agent reasoning capture in replays (injection + privacy surface).
10. "Measurement product" marketing claims — demo/testbed positioning until the
    domain-generic machinery passes one real coding-task paired A/B.
11. helios hot tier (M6) — ladder/lineage stay on SQLite + external durable store.
12. `agentdex.builders` custom-domain wiring — stays parked; host is
    `agentdex.ai-builders.space`.

## Consequences

- ADR-0009's external-language rule relaxes ONLY for the arena lane: "battle" is
  permitted in arena-scoped surfaces (`packages/adx_showdown/`, `packages/agentdex_arena/`,
  arena docs); expedition/co-opetition language remains the default elsewhere.
- `IDEAL_EXPERIENCE.md` gains §Arena with falsifiable clauses A1–A8 (the "Not a battle"
  anti-pattern is amended in place to point here).
- `EVAL.md` gains §Arena criteria; `AUTONOMY_THRESHOLD.md` gains the visiting-agent
  ladder L0–L3.
- The ai-builder-coach MCP remains a **build-time dev tool** (ADR-0005 clarification
  upheld; ADR-0004 hub-cache pattern governs its use) — never a runtime dependency.
