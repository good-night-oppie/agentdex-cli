---
title: M2 WU-7 ARC local real engine + free measured run capsule
status: active
owner: harness-41
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: M2
layer: cross-cutting
cross_cutting: true
enforced_by:
  - packages/adx_ladders/tests/test_local_arc_engine.py
  - packages/agentdex_cli/tests/test_measure_cmd.py
verifiable_claims:
  - Product-code edits are dispatched through model_route execute.
  - A genuine (non-fake) local ARC engine produces a measured run with cost_is_measured true and zero declared-budget fallback.
  - The local engine is honestly non-leaderboard (self_reported, no scorecard).
---

# M2 WU-7: ARC local REAL engine + FREE scripted-heuristic measured run

You are an execute-tier coding worker in `/home/admin/gh/agentdex-cli-redesign` on branch `redesign/evolution-market`.

Hard routing contract from the operator: product code edits may be made by you, via this `model_route.sh execute` dispatch. The coordinator will review/test/commit/push. Do **not** commit or push.

## Context
Audit finding (evidence/M2/audit-summary.md): only fake-engine (proxy) runs exist. We need a GENUINE MEASURED run of the ARC adapter machinery. The hosted ARC-AGI-3 SDK is NOT installed and needs written permission + a key, so v1's free genuine measured run is a **local deterministic ARC-style engine** driven by a **scripted-heuristic candidate (no LLM, $0)**. This is "measured" (real subprocess play, real wall clock, real dynamics-driven quality) as opposed to "fake" (hardcoded score). It must be HONESTLY non-leaderboard.

Existing shape (read these first):
- `packages/adx_ladders/src/adx_ladders/adapters/arc_agi3.py` — `ArcEngineProtocol` (reset/step/score/scorecard_id), `ArcAgi3Adapter(engine, game_ids, cost_dollar=..., max_steps_per_episode=...)`. Timed-out runs report quality=0 and self_reported receipt. When `cost_dollar` is passed it is treated as measured (cost_is_measured=True from the P2 fix already landed).
- `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` — `_build_adapter(ladder_id, engine_fake=...)`, `--engine-fake` forces `kind=fake_engine` non-leaderboard receipts. Exit codes `_EXIT_OK=0`, `_EXIT_GATE=2`, `_EXIT_NO_ADAPTER=3`.
- `packages/agentdex_cli/src/agentdex_cli/_fakes.py` — the FAKE engines (do NOT put the real engine here).

## Required work

1. **Real local ARC engine** — add a genuine deterministic engine implementing `ArcEngineProtocol`, NOT a hardcoded-score stub. Put it in `packages/adx_ladders/src/adx_ladders/engines/local_arc.py` (new `engines` subpackage). Design:
   - A small deterministic grid game whose outcome is actually determined by the sequence of actions the candidate sends (e.g. navigate an agent cell to a goal cell on a fixed seeded grid; quality = normalized progress toward / reaching the goal, in [0,1]).
   - `reset(game_id)` returns a real observation frame (grid + agent/goal positions); `step(action)` applies the action to real internal state and returns the next frame + `done`; `score()` returns the real achieved quality from final state; `scorecard_id()` returns `None` (no third-party authority — local runs are never verified/leaderboard).
   - Deterministic given a seed derived from `game_id` so the measured run is reproducible.

2. **Scripted-heuristic candidate** — add a real candidate under `.fleet-goal/evidence/M2/candidates/arc-scripted/`:
   - `candidate.yaml` (valid manifest: name, entrypoint = `python agent.py` using the current interpreter is fine to hardcode as `python3 agent.py`, mutable e.g. `["agent.py"]` — ensure the glob matches at least one real file per the new zero-match gate, base_model e.g. `scripted-heuristic-no-llm`, budget usd>0 wall_clock_min>0, ladders `["arc-agi-3"]`).
   - `agent.py` — a NO-LLM scripted heuristic that reads `{"type":"observation",...}` lines on stdin and emits `{"type":"action","action":...}` lines, choosing actions by a simple greedy heuristic toward the goal. Deterministic.

3. **CLI wiring** — extend `adx measure` with a real local-engine path distinct from `--engine-fake`. Add `--engine {fake,local-arc}` (default `fake` for back-compat) OR a `--engine-local-arc` flag; pick one and keep existing `--engine-fake` behavior intact. When local-arc is selected for ladder `arc-agi-3`, build `ArcAgi3Adapter(LocalArcEngine(...), game_ids=[...], cost_dollar=0.0)` so cost is a MEASURED $0 (cost_is_measured=True), and do NOT force a fake receipt — the adapter's honest self_reported/no-scorecard receipt stands. local-arc for any non-arc ladder must error cleanly (exit `_EXIT_NO_ADAPTER`).

4. **Honesty invariants (critical):**
   - The local-arc receipt MUST be `tier=self_reported` and MUST NOT carry a scorecard/verified ref (local runs are never leaderboard-eligible).
   - `cost_is_measured` MUST be True and `cost_dollar` MUST be `0.0` (real zero spend, no LLM) — never the declared budget fallback.
   - Keep frontier axes exactly quality/cost_dollar/wall_clock_sec.

5. **Tests** — add:
   - engine unit tests (deterministic outcomes; a good action sequence scores higher than a bad one; score in [0,1]).
   - a measure-cmd test that runs `--engine local-arc --ladder arc-agi-3` end-to-end on the scripted candidate and asserts: exit 0, real axes, `cost_is_measured` True, `cost_dollar==0.0`, receipt tier self_reported and NOT kind=fake_engine, quality is a real number in [0,1].
   - a test that `--engine local-arc --ladder tb2` errors cleanly.

## Run the focused suite

```bash
uv run pytest packages/adx_ladders/tests packages/agentdex_cli/tests/test_measure_cmd.py
```

Also produce a real measured artifact for evidence by running:

```bash
uv run adx measure --agent .fleet-goal/evidence/M2/candidates/arc-scripted --ladder arc-agi-3 --engine local-arc --out .fleet-goal/evidence/M2/measured/arc-local-scripted.json
```

(create the `.fleet-goal/evidence/M2/measured/` dir; commit the JSON — coordinator will handle commit).

## Output
Report: files changed/created, the measured JSON path + its scores/receipt/cost_is_measured, tests run + result, caveats. Do NOT commit or push.
