---
title: "SECH: Self-Evolving Codex Harness — fleet work-order"
status: draft
owner: "@EdwardTang"
created: 2026-06-19
updated: 2026-06-19
type: reference
scope: tasks/codex-harness-evolution
layer: cross-cutting
cross_cutting: true
---

# SELF-EVOLVING CODEX HARNESS (SECH) — fleet work-order SPEC

**Owner-orchestrator:** Eddie (meta-planner) · **Lineages:** adx-cli + adx-core + bene-core
**Created:** 2026-06-19 · **Home repo:** agentdex-cli · **Substrate:** ADR-0014 self-play arena
**Status:** PROPOSED (fleet program — freeze contracts first)

## North star (one sentence)

Make the **openai/codex fork** (`~/gh/codex` = `EdwardTang/every-code`) **self-evolve
its WHOLE harness** — system prompt `p`, decision protocols, sub-agent orchestration,
codex tooling, **source-code modules, and architecture** — driven by **bene
meta-harness evolution** (NOT RL) and **falsified by the agentdex Showdown self-play
arena**, à la **Continual Harness** (Karten et al. 2026, reset-free in-place harness
refinement) + **Autogenesis** (RSPL versioned resources + SEPL propose→assess→commit
with lineage + rollback). The unit of evolution is the harness-**as-code**, not a
prompt string; the arena is the kill-gate's ground truth.

## What's already true (do not rebuild)

- **Arena eval is built + proven** — A1 `run_vs_baselines` (poke-env vs PS server),
  A3 `multi_dim_fitness` (win_rate/elo + 3 anti-reward-hack guards), A4
  `arena.selfplay_battle` MCP tool. bene `evolve_battle_harness` PROVEN end-to-end
  (kill-gate ACCEPT, +25–66pp, committed artifact).
- **codex plays the arena over MCP** — `selfplay/codex_adapter.select_codex_move(harness,
  battle, *, decide)` (PR #343, Contract 5): the harness's `system_prompt`+params ARE
  codex's policy; a live codex plugs into `decide`. DONE #1 closed.
- **bene = the SEPL engine** — `evolve_battle_harness` kill-gate + lineage; a 5-store
  CRUD substrate exists (mostly inert — the Refiner is the missing operator).

## The genome — harness-AS-CODE (Autogenesis RSPL; what evolves)

A `CodexHarness` is a **versioned directory of resources**, not a string:

```
harness/<id>/
  prompt/system.md          # p — the policy text
  protocols/decide.md       # the turn protocol (observe -> plan -> act schema)
  orchestration/agents.yaml # G — sub-agent wiring (planner/executor/critic)
  tools/*.py                # codex tooling exposed at decision time
  modules/*.py              # source modules codex's policy imports (damage_calc, lookahead, ...)
  manifest.yaml             # architecture: which modules/tools/agents wire together + version + parent
```

bene mutates **any resource** (RSPL: each is versioned, has lifecycle, rollback). The
JSON/dir form is the wire to bene; `adx_showdown.harness.BattleHarness` stays the
**typed contract head** (prompt+params+strategy), extended with a `harness_ref`
pointer to the resource dir for the code/tool/module resources.

## The loop (Darwin-Gödel / Autogenesis SEPL, gated by the arena)

```
seed harness H0 (code artifact)
  └─ ACT      codex plays self-play vs HELD-OUT baselines using H   → trajectory + multi_dim fitness
  └─ OBSERVE  extract failure signatures (illegal moves, losses, stalls, tool errors)
  └─ PROPOSE  codex-as-Refiner reads trajectory+failures, emits a HARNESS MUTATION:
             a prompt rewrite | new tool | new module | code diff | architecture/orchestration change
  └─ ASSESS   apply mutation in a SANDBOX -> build/validate -> H' -> re-evaluate on HELD-OUT (fresh samples)
  └─ GATE     bene kill-gate: keep H' only if it beats H on held-out by margin (95% CI), no guard regression
  └─ COMMIT   lineage + DGM archive (keep ALL accepted harnesses for open-ended search); else ROLLBACK
repeat; report measured uplift of the best evolved harness, with the winning mutation
being a genuine CODE/TOOL/ARCHITECTURE change (not just a prompt tweak).
```

## INTERFACE CONTRACTS (freeze first — cross-lane glue)

- **Contract H — CodexHarness resource layout + loader** (adx-cli): the dir layout
  above + `load_harness(ref) -> runnable codex policy` + `harness_to_json/from_json`
  (the bene wire). Back-compat: a prompt-only harness is a valid CodexHarness.
- **Contract M — Mutation** (adx-core/codex): `{kind: prompt|tool|module|protocol|
  orchestration|architecture, target_path, diff, rationale, provenance}` — a
  JSON-serializable, applyable patch to a harness resource dir.
- **Contract R — Refiner** (adx-core): `refine(harness_ref, trajectory, failure_signatures)
  -> Mutation[]` — codex-as-coding-agent proposes harness mutations (uses `codex exec`
  on the harness dir). The autogenesis PROPOSE step.
- **Contract S — Sandbox apply+validate** (adx-core): `apply_and_validate(harness_ref,
  Mutation) -> H'_ref | reject(reason)` — apply the patch in an isolated worktree,
  build/lint/unit-test the harness modules, reject on failure (never ship a broken H').
- **Contract E — Eval** (adx-cli): `evaluate(harness_ref, run_seed, n_battles>=30) ->
  fitness + trajectory + failure_signatures` — the arena ground truth (reuses A1+A3,
  fresh held-out re-measure per the C2 DONE-evidence rules).
- **Contract G — Gate + archive** (bene-core): `evolve_codex_harness(H0, refine_fn,
  eval_fn, n_gen, run_seed) -> {best, archive, lineage, killgate_report}` — bene
  MetaHarnessSearch with the Refiner as the mutation op + the arena as fitness +
  hash-locked kill-gate + the DGM archive (open-ended, keeps accepted lineage).

## LANES (owner = live fleet lineage; tiny PRs per repo discipline)

- **adx-cli (arena substrate + harness-as-code + eval).** Owner: **adx-cli**.
  L1 live codex `decide` hook — codex plays a move via the real codex CLI driven by
     the harness prompt (Phase-1 foundation; builds on #343's seam).
  L2 `CodexHarness` resource layout + `load_harness` + JSON seam (Contract H), with
     `BattleHarness` extended by a `harness_ref` (prompt-only = valid).
  L3 failure-signature extractor from the battle trajectory (illegal/loss/stall/tool-error)
     + `evaluate()` (Contract E) reusing A1+A3 + the C2 fresh-re-measure rules.
- **adx-core (codex Refiner + sandbox apply/validate + e2e).** Owner: **adx-core**.
  C1 the **Refiner** (Contract R) — codex-as-coding-agent proposes harness mutations
     across prompt/tool/module/protocol/orchestration/architecture via `codex exec` on
     the harness dir.
  C2 **sandbox apply+validate** (Contract S) — isolated worktree, build/lint/test the
     mutated harness modules, reject broken H' (NEVER evaluate an unbuildable harness).
  C3 the e2e driver: seed → ACT → OBSERVE → PROPOSE → ASSESS → GATE → emit DONE_JSON.
- **bene-core (meta-harness evolution + kill-gate + DGM archive).** Owner: **bene-core**.
  B1 `evolve_codex_harness` (Contract G) — bene MetaHarnessSearch with the Refiner as
     the mutation operator (replacing the inert random mutate), arena fitness as the
     evaluator, hash-locked kill-gate, lineage + the **DGM archive** (open-ended).
  B2 anti-vacuous + rollback: a non-improving / unbuildable / reward-hacking H' is
     REJECTED + rolled back; assert `battles_played>0 ∧ gens>0` + the winning mutation
     is non-prompt at least once.

## Falsifiable DONE (this is "the codex fork evolves")

E2E run, reproducible from `(seed, run_seed)`, with transcript + artifact proving:
1. codex plays the arena via the MCP/CLI surface (DONE #1 ✓ #343) using harness H.
2. codex-as-Refiner proposes ≥1 **non-prompt** harness mutation (a new tool / module /
   code diff / architecture change), applied + validated in the sandbox.
3. The evolved harness **beats the seed on HELD-OUT baselines** by ≥+10pp (95% CI
   excludes 0 over ≥30 battles/matchup), on fresh re-measured samples.
4. Promotion is **kill-gated** (bene hash-locked probe) + anti-vacuous + rollback
   proven (a broken/non-improving H' is REJECTED).
5. The DGM **archive + lineage** records the accepted harness genealogy (open-ended).

## Sequencing

Freeze Contracts H/M/R/S/E/G first. adx-cli L1+L2 and bene-core B1 (mocking the
Refiner) start in parallel; adx-core C1+C2 unblock the real PROPOSE/ASSESS; integrate
at C3. Coordinate cross-lane on the A2A bus; tiny PRs per repo discipline.

## Safety rails (self-modifying code)

- Mutations apply ONLY in an isolated worktree/sandbox; build+lint+test gate before any
  eval (Contract S) — a harness that does not build is REJECTED, never run.
- No mutation touches the fleet's own infra / the live codex binary; the evolving
  artifact is a COPY of the harness resources, not the operator's codex install.
- Every accepted mutation is content-addressed + lineage-logged (auditable, rollback-able).
