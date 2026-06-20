---
title: "Self-Play Meta-Harness Evolution Spec"
status: active
owner: harness-11
created: 2026-06-19
updated: 2026-06-20
type: spec
scope: task
layer: cross-cutting
cross_cutting: true
verifiable_claims:
  - claim: Codex drives self-play through the arena MCP surface.
    enforced_by: tasks/selfplay-metaharness/artifacts/done1_codex_over_mcp.json
  - claim: The evolved harness beats the seed on held-out baselines with a nonzero confidence interval.
    enforced_by: tasks/selfplay-metaharness/artifacts/done_c2_pokeenv.json
  - claim: The real bene Lane-B evolver can run the loop behind the kill gate.
    enforced_by: tasks/selfplay-metaharness/artifacts/done_e2e_real_bene.json
  - claim: The kill gate rejects a non-improving harness.
    enforced_by: packages/adx_showdown/tests/test_selfplay_e2e_driver.py
definition_of_done: E2E DONE_JSON contains battles_played > 0, gens_completed > 0, and killgate_report.verdict == "ACCEPT".
---

# SELF-PLAY META-HARNESS EVOLUTION — fleet work-order SPEC

**Owner-orchestrator:** harness-11 · **Created:** 2026-06-19 · **Home repo:** agentdex-cli
**Status:** EVIDENCE COMPLETE (fleet build, MCP-first)

## North star (one sentence)

Let open-source **openai/codex** use **agentdex-cli** (MCP-first) to run poke-env-style
**self-play** in the Showdown arena, where improvement comes **not from RL** but from
**bene meta-harness evolution** — bene mutates codex's *battle-playing harness*, scored by a
**multi-dimensional Pareto fitness that includes self-play win-rate/Elo as one dimension**, and
promotes only kill-gate winners.

## Acceptance Criteria

- [x] Codex drives Showdown self-play battles via the agentdex-cli arena MCP surface.
- [x] Bene runs at least 1 meta-harness evolution generation mutating codex's battle harness.
- [x] The evolved harness beats the seed by at least +10 pp on held-out baselines.
- [x] The kill gate rejects a non-improving harness and asserts `battles_played > 0` plus `gens_completed > 0`.
- [x] The fitness vector records at least 3 dimensions, including win-rate or Elo and 2 anti-reward-hack dimensions.

## Translation to Enforcement

- Contract 1 is enforced by the `BattleHarness` genome type and strict model validation.
- Contract 2 is enforced by `run_selfplay_battle` and the registered `selfplay_battle` MCP tool.
- Contract 3 is enforced by `multi_dim_fitness` and held-out baseline artifacts.
- Contract 4 is enforced by bene's `evolve_battle_harness` bridge and kill-gate report.
- Contract 5 is enforced by the codex move adapter and MCP-over-self-play evidence artifact.

## Definition of Done

This run is done only when a fixed-seed E2E run, reproducible under the
current live poke-env/PS runner contract, produces transcript plus artifact
evidence that satisfies every criterion below:

1. codex drives Showdown self-play battles **via the agentdex-cli arena MCP surface** (not a bespoke script).
2. bene runs **≥1 meta-harness evolution generation** mutating codex's battle harness.
3. The **evolved harness beats the seed harness by a measured win-rate margin** on
   **held-out baseline opponents** (poke-env `RandomPlayer`, `MaxBasePowerPlayer`,
   `SimpleHeuristicsPlayer`). CI-sized C2 evidence targets ≥ +10 pp with 95% CI
   excluding 0 over ≥30 battles; real-bene E2E evidence is the substrate-gated
   `killgate_report.verdict == "ACCEPT"` plus nonzero battle/gen counts.
4. Promotion is **kill-gated** (hash-locked bene eval probe): a harness that does NOT beat seed on
   held-out is REJECTED. Anti-vacuous: assert `battles_played > 0` and `gens_completed > 0`, not
   just "gate clean".
5. The multi-dim Pareto fitness records **≥3 dimensions** incl. `win_rate`/`elo` + ≥2 anti-reward-hack
   dims (e.g. `move_legibility`, `no_forfeit_exploit`, `turn_efficiency`).

## References (agents: consult these)

- poke-env index: https://poke-env.readthedocs.io/en/stable/index.html
- poke-env self_play: https://poke-env.readthedocs.io/en/stable/examples/self_play.html
  (We **replace** the PPO/SuperSuit RL training loop with bene MetaHarnessSearch; we KEEP the
  `Player` battle surface, `cross_evaluate`, and the 3 baseline players for held-out eval.)
- agentdex-cli: `packages/adx_showdown/src/adx_showdown/selfplay/runner.py` (poke-env/PS
  self-play runner), `packages/agentdex_arena/src/agentdex_arena/{gateway,mcp_surface}.py`.
- bene: `bene/metaharness/{search,evaluator,pareto,compactor,worker}.py`, `bene/kernel/evolve/gepa.py`,
  bene eval-probe/kill-gate substrate. `uv run --project ~/gh/bene-main`.
- agentdex multi-dim/anti-reward-hack reward design: `docs/references/2026-06-12-arena-fun-multidim-rewardhack-design.md`.

## The loop

```
seed battle-harness H0
  └─> [Lane A] run_selfplay_battle(Hi, Hj, seed) via poke-env Players on a live PS server
        └─> BattleResult{winner, trace, raw_dims}
  └─> [Lane A] multi_dim_fitness(BattleResult[]) -> Pareto vector {win_rate, elo, legibility, ...}
  └─> [Lane B] bene MetaHarnessSearch.evolve(Hi, fitness_fn) -> mutated harness population
  └─> [Lane B] kill-gate probe: keep Hk only if beats seed on HELD-OUT baselines by margin
  └─> [Lane B] SharedLog lineage entry; gen += 1
repeat ≥1 gen; report measured uplift(best vs seed) on held-out.
```

## INTERFACE CONTRACTS (freeze these first — cross-lane glue; mismatch = integration hell)

### Contract 1 — BattleHarness genome (what bene mutates; Lane A defines, Lane B consumes)
```json
{ "harness_id": "str", "system_prompt": "str",
  "move_selection_strategy": "str (e.g. 'max_damage'|'type_aware'|'llm_freeform')",
  "tool_policy": { "allow_switch": true, "lookahead_depth": 1 },
  "params": { "<float/int/str knobs bene perturbs>": "..." } }
```
JSON-serializable; bene's mutation operates on `system_prompt` + `params` + `move_selection_strategy`.

### Contract 2 — Battle runner (Lane A exposes; codex drives over MCP)
`run_selfplay_battle(harness_a, harness_b, seed:int, n_battles:int) -> BattleResult`
where `BattleResult = { winner, battles: [...], trace_path, raw_dims: {wins_a, turns, forfeits, illegal_moves, ...} }`.
Seeded and reproducible-in-distribution against the live poke-env/PS runner; exact `(seed, inputLog)` byte replay remains an ADR-0014 open item.
**MCP tool name:** `selfplay_battle` on `mcp_surface.py` (codex calls this).

### Contract 3 — Multi-dim Pareto fitness (Lane A exposes; Lane B's evaluator consumes)
`multi_dim_fitness(results: BattleResult[]) -> { "win_rate": float, "elo": float, "move_legibility": float, "no_forfeit_exploit": float, "turn_efficiency": float }`
win_rate/elo computed vs the **held-out baselines**; anti-reward-hack dims penalize forfeit-farming /
illegal-move spam / stalling (per the rewardhack-design doc).

### Contract 4 — Evolution entrypoint (Lane B exposes; Lane C/e2e drives)
`evolve_battle_harness(seed_harness, fitness_fn, n_gen:int, run_seed:int) -> { best, lineage, killgate_report }`
backed by bene `MetaHarnessSearch` + `pareto.py`; `killgate_report` asserts best beats seed on held-out.

### Contract 5 — codex adapter (Lane C; the agent-under-evolution)
`selfplay_battle` is the batch MCP surface codex drives. Per-turn move decisions are
resolved in-process by `adx_showdown.selfplay.runner`: codex strategies route the
current `BattleHarness` plus battle state through `select_codex_move` (and, when
live codex is enabled, its `decide` hook). The harness's `system_prompt`+`params`
ARE codex's policy. This is the thing being evolved.

## LANES (owner = live fleet session; build as tiny PRs per repo discipline)

- **Lane A — agentdex-cli arena self-play surface (MCP-first).** Owner: **adx-cli-7** (+adx-core support).
  A1 `run_selfplay_battle` over poke-env Players on a live PS server.
  A2 `BattleHarness` genome type + seed harness H0 (Contract 1).
  A3 `multi_dim_fitness` incl. win-rate/Elo + ≥2 anti-reward-hack dims; port poke-env Random/MaxBasePower/SimpleHeuristics as held-out baselines (Contract 3).
  A4 expose `selfplay_battle` MCP tool on `mcp_surface.py` (Contract 2) + current runner reproducibility.
- **Lane B — bene meta-harness evolution bridge.** Owner: **bene-core-6**.
  B1 `evolve_battle_harness` driving `MetaHarnessSearch` to mutate the BattleHarness genome (Contract 4).
  B2 Pareto evaluator wired to Contract-3 fitness vectors.
  B3 hash-locked **kill-gate** eval probe (evolved must beat seed on held-out by margin) + anti-vacuous assert.
  B4 SharedLog lineage + current-runner reproducibility receipt; exact `(run_seed, inputLog)` byte replay
  stays an ADR-0014 open item.
- **Lane C — codex self-play agent adapter + E2E.** Owner: **codex** (+harness-11 integrate).
  C1 codex battle-harness adapter: codex strategies pick moves from `BattleHarness`+state in-process via
  `select_codex_move` (Contract 5).
  C2 e2e driver: seed → self-play → fitness → evolve ≥1 gen → measure uplift on held-out; emit `DONE_JSON`.
- **Lane D — verify (anti-vacuous).** Owner: **og** (+harness-11). Triple-verify the uplift isn't vacuous:
  held-out opponents real, `battles_played>0 ∧ gens_completed>0`, kill-gate actually rejects a non-improving harness.

## Sequencing / dependencies

Freeze Contracts 1–5 first (this doc). Then A1/A2 and B1 can start in parallel (B mocks Contract-3
fitness until A3 lands). A3 + A4 unblock real C2. D runs after C2 produces a candidate. Integrate at C2.

## Repo discipline

Tiny PRs per lane (worktree + local-gate + push + CI + review), per each repo's existing discipline
(agentdex-cli: no branch-protection, doc-lint is the real gate; bene-main: kill-gate convergence).
Indivisible new modules may use the indivisible-marker override. Coordinate cross-lane on the A2A bus.
