---
title: "M2 WU-8F fix capsule — coordinator review findings on HarborCliClient (3 fixes + regression tests)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "run_task MUST NOT deadlock on a chatty child (no un-drained PIPEs), MUST hard-cap tasks per invocation (-l 1), and measure-time ValueError MUST surface as a clean stderr message + nonzero exit, never a traceback"
    test: "packages/adx_ladders/tests/test_harbor_cli_client.py + packages/agentdex_cli/tests/test_measure_cmd.py (regressions land with this fix)"
---

# M2 WU-8F — HarborCliClient coordinator-review fixes

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
Fix EXACTLY the three findings below in the files named. READ FIRST:
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`,
`packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` (lines ~195-210),
`.fleet-goal/evidence/M2/harbor-cli-surface.md` (real flag semantics).

## Guardrails (hard)

- Touch ONLY: `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`,
  `packages/adx_ladders/tests/test_harbor_cli_client.py`,
  `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`,
  `packages/agentdex_cli/tests/test_measure_cmd.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM runs. Tests stay hermetic
  (stub harbor binary pattern already in the test file).
- One regression test per finding, marked with the finding id in the test
  docstring.

## F1 (P1) — pipe-full deadlock defeats run honesty

`run_task` spawns harbor with `stdout=PIPE, stderr=PIPE` then calls a bare
`proc.wait()` — NOTHING drains the pipes. A harbor run writing more than the
OS pipe buffer (~64KB) blocks forever on a full pipe, gets killed at
`timeout_sec`, and a PASSING chatty run is misreported as
`timed_out=True/passed=False`. Same failure class as the WU-6 stdin-deadlock
P1, on the read side.

FIX: redirect child stdout+stderr to an on-disk log file
`<jobs_dir>/<job_name>.harbor.log` (single merged file: pass the same handle
as `stdout` and `stderr=subprocess.STDOUT`), opened before `Popen`, closed in
a `finally`. Keep `stdin=DEVNULL`, `start_new_session=True`, and the existing
`_kill` escalation unchanged. The log file is diagnostic evidence — do NOT
delete it on failure.

REGRESSION TEST: stub harbor writes >128KB to stdout, then writes a passing
trial `result.json`, exits 0 well within `timeout_sec` → assert
`passed=True, timed_out=False` (this hangs/fails on the unfixed code).

## F2 (P2) — unbounded glob match

`-i/--include-task-name` supports glob patterns; a task_id containing glob
chars could match MANY tasks in one invocation while the adapter accounts for
exactly one. Real flag map: `-l/--n-tasks` = max tasks applied after filters;
`-n` = `--n-concurrent` (concurrency, not task count).

FIX: append `"-l", "1"` to the argv (keep `-n 1`). Correct the module
docstring's invocation sketch to note `-n 1` = concurrency and `-l 1` = hard
task cap.

REGRESSION TEST: assert the stub receives both `-l 1` and `-n 1` in its argv
(stub already records argv — extend the assertion).

## F3 (P2) — measure-time ValueError tracebacks

`measure_cmd.py` line ~205: `result = adapter.measure(candidate)` is OUTSIDE
any try. With `--engine harbor-cli` (binary present) and no CLI wiring for
`tasks=`, `HarborCliClient.list_tasks` raises `ValueError` at measure time →
raw traceback to the user.

FIX: wrap the `adapter.measure(candidate)` call in
`try/except ValueError as exc: print(str(exc), file=sys.stderr); return 1`
(mirror the pre_run_check handling directly above it).

REGRESSION TEST: in `test_measure_cmd.py`, with a stub harbor binary on PATH
(so construction succeeds) and a tb2 candidate, run the CLI with
`--engine harbor-cli` → assert exit code 1 and the ValueError message on
stderr, no traceback.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed).

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
