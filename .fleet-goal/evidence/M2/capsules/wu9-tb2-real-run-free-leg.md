---
title: "M2 WU-9 request capsule — $0 GENUINE real-Harbor TB2 measured run (oracle + no-op candidate; NO paid LLM)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The TB2 free-leg evidence MUST come from a REAL harbor run against a REAL TB2 task in its REAL Docker environment (never a stub), MUST be honestly labeled (no-op candidate quality=0, self_reported receipt, non-leaderboard), and MUST NOT invoke any paid/hosted LLM"
    test: "packages/agentdex_cli/tests/test_measure_cmd.py --harbor-tasks regressions (land with this WU) + .fleet-goal/evidence/M2/measured/tb2-harbor-noop.json inspected by coordinator"
---

# M2 WU-9 — $0 genuine real-Harbor TB2 measured run

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST:
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py` (WU-8 client —
flags, jobs layout, tasks= fallback),
`.fleet-goal/evidence/M2/harbor-cli-surface.md` (real CLI surface),
`packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` (WU-7/8 --engine
pattern), `.fleet-goal/evidence/M2/candidates/arc-scripted/` (WU-7 candidate
precedent), `.fleet-goal/evidence/M2/measured/arc-local-scripted.json`
(measured-evidence file shape precedent).

## Context

harbor 0.18.0 is INSTALLED; Docker 29.6.1 is live. TB2's oracle agent
replays the human oracle solution — no LLM, $0. A no-op custom agent
exercises OUR candidate pipe end-to-end for $0 (honest quality=0). Per
operator directive: NO paid LLM run of any kind. This WU produces the
genuine TB2 evidence legs so only the PAID leaderboard-comparable run
remains behind the operator fork.

## Guardrails (hard)

- Touch ONLY:
  `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` (+ its tests),
  `.fleet-goal/evidence/M2/candidates/tb2-noop/` (new candidate dir),
  `.fleet-goal/evidence/M2/measured/` (new evidence JSON files),
  `.fleet-goal/evidence/M2/harbor-agent-api.md` (new evidence note).
  NOTHING else.
- Do NOT `git commit` / `git push`.
- **NO paid/hosted LLM**: never pass `-m`/model pointing at a hosted LLM;
  agents are `oracle` (builtin) and the local no-op module ONLY.
- Exactly ONE task per real run (`-i <exact-task-name>` + `-l 1`). Cap each
  real run's wall clock at 20 minutes (candidate budget.wall_clock_min=20);
  a timeout is an honest result, not a failure of this WU — file it.
- Unit tests stay hermetic (stub harbor pattern); the REAL runs are
  operations steps, not tests.

## Part 1 — CLI tasks injection (code + hermetic tests)

`measure_cmd.py`: add `--harbor-tasks <comma-separated task names>`;
forwarded as `HarborCliClient(tasks=tuple(...))` for `--engine harbor-cli`.
Reject (clean stderr + exit 2): empty/whitespace items, use with any other
engine. Regression tests via the existing stub-harbor pattern: forwarding
works end-to-end; rejection paths.

## Part 2 — no-op custom agent candidate

- Read the installed harbor package source (`uv tool` venv) to find the
  REAL custom-agent API (`-a module:Class` contract — constructor/methods
  harbor calls). Document verbatim findings in
  `.fleet-goal/evidence/M2/harbor-agent-api.md` (frontmatter like
  harbor-cli-surface.md: layer cross-cutting + cross_cutting true; put
  quoted upstream excerpts under a `## Background` H2).
- `.fleet-goal/evidence/M2/candidates/tb2-noop/`: `candidate.yaml`
  (name tb2-noop, ladders [tb2], base_model "none-no-llm", budget
  {usd: 0.0, wall_clock_min: 20}, mutable per WU-1 gate) + the no-op agent
  module implementing that real API (performs no actions / immediately
  completes; MUST be importable by harbor inside its run context — check
  how harbor resolves the import path and document it).
- If candidate.yaml validation rejects budget usd=0.0 (check the WU-1
  gate), use the smallest accepted value and note it in the evidence.

## Part 3 — the two $0 REAL runs (operations)

Pick ONE real TB2 task: discover a small/quick task name from the dataset
via harbor's own tooling (e.g. `harbor task download` / registry metadata /
the HF dataset listing already cached by harbor). Record the exact task
name + how you found it in the evidence note.

1. **Oracle leg (engine integration):**
   `harbor run -d terminal-bench/terminal-bench-2 -i <task> -a oracle -o <evidence jobs dir> --job-name wu9-oracle -n 1 -l 1`
   → write `.fleet-goal/evidence/M2/measured/tb2-harbor-oracle.json`:
   {task, passed, wall_clock_sec, harbor_version, job_dir artifact paths,
   note: "builtin oracle agent, no LLM, engine-integration evidence —
   not a candidate measurement"}.
2. **Candidate-pipe leg (through OUR stack):**
   `uv run adx measure --agent .fleet-goal/evidence/M2/candidates/tb2-noop --ladder tb2 --engine harbor-cli --harbor-tasks <task> --out .fleet-goal/evidence/M2/measured/tb2-harbor-noop.json`
   Expected: quality=0.0 (honest), receipt self_reported/raw_artifacts,
   real harbor job artifacts on disk. Whatever cost_is_measured comes out
   of the honest pipeline is the answer — do NOT fudge it.

If Docker image pull or task setup fails, capture the exact error in the
evidence note and stop — that is a finding, not something to work around
with fakes.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)
- Both measured JSON files exist with REAL harbor job artifact paths that
  exist on disk.

## Return contract (four fields ONLY)

1. What was learned (incl. real harbor agent API + task-discovery surprises)
2. What changed (file list)
3. Supporting evidence (test output + both real-run summaries verbatim)
4. What should happen next
