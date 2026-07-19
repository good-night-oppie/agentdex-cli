---
title: "M2 WU-12 fix capsule — measure CLI contract: --engine conflict detection, exit-code consistency, durable --jobs-dir + receipt"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "adx measure MUST reject a --engine-fake + --engine <real> conflict (never silently override); the --harbor-tasks-missing error MUST use the same exit-2 gate convention as its sibling rejections; and --jobs-dir MUST let a measured run land harbor artifacts in a durable path the receipt then references"
    test: "packages/agentdex_cli/tests/test_measure_cmd.py (regressions land with this fix)"
---

# M2 WU-12 — measure CLI contract hardening (re-audit P2 #10, P3 #11, P2 #3, P3 #7)

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `.fleet-goal/evidence/M2/audit-summary-round2.md`,
`packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`
(`_resolve_engine_mode` ~91-98, `cmd_measure` ~169-276, exit codes
`_EXIT_OK=0 / _EXIT_GATE=2 / _EXIT_NO_ADAPTER=3` ~46-48, arg parser ~279-end),
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`
(`HarborCliClient(__init__ jobs_dir=...)` ~51-74).

## Findings (all in the measure CLI contract — one logical unit, one file + tests)

- **P3 #11** `_resolve_engine_mode` returns `_ENGINE_FAKE` FIRST, so
  `--engine-fake --engine harbor-cli` silently runs FAKE, discarding the
  explicit real engine. No conflict detection.
- **P2 #10** `--harbor-tasks` with a wrong engine already exits 2 (gate), but
  the "missing tasks" ValueError path (`HarborCliClient.list_tasks` with no
  `tasks=`) exits 1 with an internal-API message — inconsistent with the
  flag's own exit-2 rejection convention and opaque to the user.
- **P2 #3 / P3 #7** Default `jobs_dir` is `tempfile.mkdtemp` (/tmp); a
  measured run's self_reported receipt then cites ephemeral (/tmp +
  gitignored) artifacts that vanish. There is no CLI way to place harbor job
  artifacts in a durable path.

## Guardrails (hard)

- Touch ONLY: `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`,
  `packages/agentdex_cli/tests/test_measure_cmd.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM / NO real harbor runs.
- Preserve every existing exit-code contract + honest receipt behavior.

## Fix

1. **P3 #11 conflict detection** — `_resolve_engine_mode` (or `cmd_measure`
   before build): if BOTH `engine_fake` is set AND `--engine` is an explicit
   NON-fake value, print a clear conflict message to stderr and return
   `_EXIT_GATE` (2). `--engine-fake` alone, `--engine fake` alone, and
   `--engine-fake --engine fake` (same intent) stay allowed. Do this in
   `cmd_measure` so it can return the exit code (keep `_resolve_engine_mode`
   pure or have it raise a ValueError the caller maps to exit 2 — your call,
   documented).
2. **P2 #10 exit consistency** — the "`--harbor-tasks` present but engine
   can't consume it / tasks missing" user-error family should all exit
   `_EXIT_GATE` (2) with an actionable message, not exit 1. Specifically:
   when `--engine harbor-cli` is selected WITHOUT `--harbor-tasks`, detect it
   up front in `cmd_measure` and return exit 2 with
   "`--engine harbor-cli requires --harbor-tasks <task[,task...]>`" rather
   than letting it reach the measure-time `list_tasks` ValueError (exit 1).
   Keep the measure-time ValueError catch as a backstop.
3. **P2 #3 / P3 #7 durable artifacts** — add `--jobs-dir <path>` to the
   parser; when provided with `--engine harbor-cli`, pass it to
   `HarborCliClient(jobs_dir=...)` so harbor artifacts land in the durable
   path (the receipt then references stable locations). When omitted, keep
   today's mkdtemp default (ephemeral CLI use stays convenient). Reject
   `--jobs-dir` with a non-harbor engine → exit 2 (same convention).

## Tests

- P3 #11: `--engine-fake --engine harbor-cli` → exit 2 + conflict message;
  `--engine-fake` alone still runs; `--engine-fake --engine fake` allowed.
- P2 #10: `--engine harbor-cli` with NO `--harbor-tasks` → exit 2 +
  actionable message (not exit 1, no traceback).
- P2 #3/P3 #7: `--jobs-dir <tmp_path>` with a stub-harbor fake run → harbor
  job artifacts + the emitted receipt reference paths UNDER that dir;
  `--jobs-dir` with `--engine local-arc` → exit 2.
- Existing exit-code + happy-path tests stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
