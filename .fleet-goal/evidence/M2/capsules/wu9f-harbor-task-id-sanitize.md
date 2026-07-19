---
title: "M2 WU-9F fix capsule — sanitize task-id in HarborCliClient job names; retire the org/name→*name glob rewrite"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "HarborCliClient MUST pass the caller's task id to harbor's -i filter EXACTLY as given (org-prefixed ids included) and MUST NOT let a task id shape break on-disk job/log paths; measure_cmd MUST NOT rewrite task ids into globs"
    test: "packages/adx_ladders/tests/test_harbor_cli_client.py + packages/agentdex_cli/tests/test_measure_cmd.py (regressions land with this fix)"
---

# M2 WU-9F — task-id sanitize fix

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`
(`run_task` job_name + harbor_log construction),
`packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`
(`_slash_safe_harbor_task` — the workaround you are retiring),
`.fleet-goal/evidence/M2/harbor-agent-api.md` +
`.fleet-goal/evidence/M2/capsules/wu9-tb2-real-run-free-leg.md` (context:
WU-9 found full-package dataset ids are org-prefixed `terminal-bench/regex-log`
and the glob rewrite was a stopgap because job filenames embed task_id).

## Why (defect)

The `org/name → *name` glob rewrite in `measure_cmd` can match a DIFFERENT
task sharing the suffix (e.g. `foo-regex-log`) — `-l 1` caps the count but
not which task runs, so a measured run could silently measure the wrong
task. The root cause is client-side: `HarborCliClient.run_task` embeds the
raw `task_id` in `job_name` and the `.harbor.log` filename, so a `/` breaks
`open()`.

## Guardrails (hard)

- Touch ONLY: `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`,
  `packages/adx_ladders/tests/test_harbor_cli_client.py`,
  `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`,
  `packages/agentdex_cli/tests/test_measure_cmd.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM runs; NO real harbor runs
  (hermetic stub tests only — the $0 evidence already exists).

## Fix

1. `harbor_cli.py`: derive a filesystem-safe slug for job/log names —
   `_fs_slug(task_id)`: replace every char outside `[A-Za-z0-9._-]` with
   `_`; use the slug in `job_name` and the `.harbor.log` filename ONLY.
   The EXACT `task_id` string still goes to `-i` and to
   `_parse_job_result(task_id=...)` matching. Docstring: exact-id filter,
   slugged filenames.
2. `measure_cmd.py`: delete `_slash_safe_harbor_task` and pass task ids
   through verbatim (keep the empty/whitespace-item rejection). Update the
   `_parse_harbor_tasks` docstring accordingly.
3. Note for evidence continuity: WU-9's committed artifacts keep their
   `adx-*regex-log-…` names — do NOT rename historical evidence.

## Tests

- New: org-prefixed task id `org/task-x` → stub receives `-i org/task-x`
  EXACTLY; job dir + `.harbor.log` exist with slugged (slash-free) names;
  result parsed (stub writes `task_name: org/task-x`) → passed honored.
- Update the existing WU-9 slash-rewrite regressions in
  `test_measure_cmd.py` to assert verbatim pass-through (no glob).
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
