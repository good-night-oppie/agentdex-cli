---
title: "M2 spike 1 — weco economics, empirical (new account)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

actual_route: coordinator_inline_exception (environment-bound credentialed test — orch-proj rule 8, local thread)

# M2 spike 1 — weco economics (empirical, 2026-07-11)

## What was learned

Operator authenticated a fresh Weco account on this host ("weco is
authenticated with new empirical Weco"). Measured facts:

1. **Free grant: 20.00 credits**, dollar-denominated (per-step costs in $).
2. **3-step toy run cost $0.17 total** on the default model
   (`gemini-3-flash-preview`): step 0 baseline eval $0.00, steps 1–3 =
   $0.03/$0.09/$0.05. `weco credits cost <run_id>` per-step/per-node table
   matches the balance delta (20.00 → 19.83) exactly — billing is transparent
   and auditable per step. Grant ≈ 350 toy-scale steps; real candidate runs
   with bigger diffs/context will cost more per step.
3. **CLI surface (v matching `weco --help` this host):** verbs
   `run/login/logout/credits/resume/share/setup/observe/start`.
   - `weco start claude` EXISTS (D2 driver mechanism empirically verified).
   - `weco share <run_id>` creates a public share link per-run —
     user-initiated; this is the sanctioned M5 display surface for weco
     lineage (agentdex never pulls from Weco; user shares the public link).
   - `weco credits {balance,topup,cost,autotopup}` — programmatic economics.
   - Contract flags relevant to `adx evolve`: `--eval-timeout`, `--save-logs`
     (per-step code snapshots under `.runs/<run-id>/`), `--apply-change`,
     `--require-review` (agent-in-the-loop), `--daemon`, `--no-auto-resume`,
     eval backends `shell|langsmith|langfuse`.
4. **BYO `--api-key`: flag exists; supported providers are gemini, openai,
   anthropic ONLY** (default models: gemini-3-flash-preview / o4-mini /
   claude-opus-4-5). The operator-offered `~/.sakana` token (`fish_…`, Sakana
   AI) is NOT a supported provider and there is no base-URL override —
   **BYO-vs-credits differential remains UNMEASURED** pending a
   gemini/openai/anthropic key. The "free on your own subscriptions" copy
   must NOT be published until this is measured (docs imply BYO keys shift
   LLM cost to the provider, but whether Weco still charges platform credits
   per step is unverified).

## What changed

None in-repo. Toy project + logs under the session job dir
(`~/.claude/jobs/40bde33d/tmp/weco_spike1/`); run id
`a60407b1-abf1-4cb0-aadb-8b8e866bb5a7` on the new account.

## Supporting evidence

- `weco credits balance`: 20.00 → 19.83 across the run.
- `weco credits cost a60407b1-…`: per-step table ($0.00/$0.03/$0.09/$0.05).
- `weco run` log: 3 steps + baseline, plans + metrics streamed; final best
  0.008144 (toy metric irrelevant to economics).
- `weco --help` / `weco run --help` / `weco start --help` captured this host.

## What should happen next

- Measure the BYO differential when a supported-provider key is available
  (one 3-step run with `--api-key gemini|openai|anthropic=…`, compare
  `credits cost`).
- Feed the contract flags into the M4 `adx evolve` driver design
  (`--save-logs` gives per-step code snapshots = candidate lineage artifacts
  for the self-reported receipt tier).
