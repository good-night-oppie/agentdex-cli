---
title: "M2 WU-10 fix capsule — P1 gate bypass: confine _find_trial_result to the verifier-written trial-root result.json (no rglob of the agent-writable subtree)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The pass/fail + cost gate MUST read only the depth-1 verifier-written <job_dir>/<trial>/result.json, never a result.json planted anywhere in the agent-writable trial artifact subtree; a candidate-planted forged result.json MUST NOT be able to set passed=True or a measured cost"
    test: "packages/adx_ladders/tests/test_harbor_cli_client.py (adversarial forged-result regression lands with this fix)"
---

# M2 WU-10 — P1: confine trial-result discovery to the verifier-written path

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `.fleet-goal/evidence/M2/audit-summary-round2.md` (the P1
finding + verified failure scenario),
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py` (`_find_trial_result`
lines ~210-234, `_parse_job_result` ~158-208),
`.fleet-goal/evidence/M2/measured/wu9-oracle-jobs/wu9-oracle/` (REAL job
layout: `result.json` at job root = JobResult; `regex-log__N2roHLD/result.json`
= genuine trial result, task_name `terminal-bench/regex-log`; forged files
would land under `<trial>/artifacts/logs/artifacts/`).

## The defect (P1, adversarially confirmed)

`_find_trial_result` does `job_dir.rglob("result.json")` and skips only the
depth-0 job-level file. Harbor copies the UNTRUSTED candidate container's
`/logs/artifacts` into `<trial>/artifacts/logs/artifacts/` (proven by WU-9
`manifest.json`), which is under `job_dir` and walked by rglob. A candidate
plants `result.json` (task_name=requested id, reward=1.0, cost_usd=0.0); the
genuine verifier file (canonical org-prefixed task_name) mismatches a bare
`--harbor-tasks` id and drops to `fallback`, the forged file becomes the sole
`matches[0]` → `passed=True` + fabricated measured $0 cost in the receipt.

## Ground truth (real Harbor 0.18.0 layout)

- `<job_dir>/result.json` — job-level JobResult (depth 0, IGNORE).
- `<job_dir>/<trial-name>/result.json` — the GENUINE verifier-written trial
  result (depth 1, direct child dir of job_dir). This is the ONLY trustworthy
  source. `-l 1 -n 1` ⇒ exactly ONE trial dir per job.
- Anything deeper (`<trial>/artifacts/...`) is agent-writable → NEVER trust.

## Guardrails (hard)

- Touch ONLY:
  `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`,
  `packages/adx_ladders/tests/test_harbor_cli_client.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM / NO real harbor runs
  (hermetic stub tests only).
- Do NOT rename or alter existing WU-9 evidence artifacts.

## Fix

Rewrite `_find_trial_result(job_dir, *, task_id)` to be PATH-CONFINED:

1. Enumerate ONLY the direct child directories of `job_dir`
   (`[p for p in job_dir.iterdir() if p.is_dir()]`) — the trial dirs. Do NOT
   rglob.
2. Candidate result files are EXACTLY `<trial_dir>/result.json` (depth-1
   trial root), never anything under it. Collect the ones that exist and are
   readable JSON dicts.
3. Selection:
   - If exactly one trial-root result.json exists → return it (the `-l 1`
     invariant; this is the genuine verifier file regardless of task_name,
     because the path — not the payload — establishes trust).
   - If more than one → prefer the one whose `task_name` equals `task_id`
     OR whose `task_name`'s trailing path segment (`task_name.rsplit("/",1)[-1]`)
     equals `task_id`'s trailing segment (handles org-prefixed vs bare);
     if still ambiguous return None (honest: cannot bind a unique trial).
   - If none → return None.
4. Delete the old `rglob` + `fallback` logic entirely. Update the docstring
   to state the trust model: path confinement (depth-1 trial root only),
   agent-writable subtree never read.

`_parse_job_result` is unchanged downstream (still returns passed=False /
cost None when `_find_trial_result` yields None — an honest non-measurement).

## Tests (hermetic)

- **Adversarial forged-result regression (the P1):** stub writes the genuine
  `<job>/<trial>/result.json` (reward 0.0, canonical task_name
  `terminal-bench/regex-log`) AND a forged
  `<job>/<trial>/artifacts/logs/artifacts/result.json` (reward 1.0,
  task_name `regex-log`, cost_usd 0.0). Run with `--harbor-tasks regex-log`
  (bare id). Assert `passed is False` and `cost_dollar is None` (or the
  genuine values) — the forged file MUST be ignored. This test FAILS on the
  unfixed rglob code.
- Genuine happy path still parses the depth-1 trial result (org-prefixed
  task_name, bare requested id) → passed honored.
- No trial dir / empty job dir → None → passed=False, honest.
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim, incl. the forged-result test)
4. What should happen next
