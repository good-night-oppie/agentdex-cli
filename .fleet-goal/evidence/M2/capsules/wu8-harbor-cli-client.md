---
title: "M2 WU-8 request capsule — real Harbor CLI client for tb2 (free leg: code + hermetic tests, NO paid run)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The Harbor CLI client MUST be grounded in the real installed harbor CLI surface (help output captured as evidence), MUST enforce per-task timeouts with process-group kill + stdin closed, MUST propagate measured per-task cost when harbor reports it (else None so the adapter's declared-budget fallback sets cost_is_measured=False), and MUST NOT execute any paid-LLM run"
    test: "packages/adx_ladders/tests/test_harbor_cli_client.py (lands with this WU)"
---

# M2 WU-8 — real Harbor CLI client (`HarborCliClient`)

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST:
`packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py` (the
`HarborProtocol` you are implementing: `run_task(task_id, agent_cmd,
timeout_sec) -> HarborTaskResult`, `list_tasks(suite) -> list[str]`;
`HarborTaskResult(passed, log_path, cost_dollar=None, timed_out=False)`),
`packages/adx_ladders/src/adx_ladders/adapters/arc_agi3.py` (`_spawn` /
`_kill` — the WU-6-hardened subprocess idioms you MUST mirror:
`start_new_session=True`, killpg SIGTERM→grace→SIGKILL),
`packages/adx_ladders/src/adx_ladders/engines/local_arc.py` +
`packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` (WU-7 `--engine`
wiring pattern), and `.fleet-goal/evidence/M2/capsules/wu6-gate-hardening-fixes.md`
(P1 lessons: stdin deadlock defeats budget kill; grandchildren leak without
process-group kill).

## Context

Terminal-Bench 2's official harness is Harbor (Apache-2.0):
`uv tool install harbor`; `harbor run -d terminal-bench/terminal-bench-2
-a oracle|claude-code|... [-m <model>]`; custom agents inject via
`--agent-import-path "module:Class"`; Docker required for real runs
(primary-source cites in `.fleet-goal/evidence/M1/research/brief-benchmarks.json`).
The tb2 adapter (WU-4) runs against an injected `HarborProtocol`; unit tests
use fakes. This WU lands the REAL client so that a genuine measured TB2 run
needs only an operator credentials/budget decision (paid leg) — or a $0
oracle / no-op-candidate run (free leg, later WU).

## Guardrails (hard)

- Touch ONLY:
  `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py` (new),
  `packages/adx_ladders/src/adx_ladders/engines/__init__.py` (export),
  `packages/adx_ladders/tests/test_harbor_cli_client.py` (new),
  `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` (extend `--engine`),
  `packages/agentdex_cli/tests/test_measure_cmd.py` (extend). NOTHING else.
- Do NOT `git commit` / `git push`.
- **NO paid-LLM execution of any kind.** You MAY `uv tool install harbor`
  (free, Apache-2.0) to ground the client in the real CLI; you MUST NOT run
  any harbor invocation that calls an LLM (`-a oracle --help`-style
  inspection and `--help` surfaces only; no `harbor run` against real tasks
  in this WU — the measured run is a separate WU).
- Unit tests MUST be hermetic: no network, no Docker, no real harbor — use a
  stub `harbor` executable (temp dir prepended to PATH) that mimics the REAL
  captured CLI surface.

## Step 1 — ground truth (evidence first)

`uv tool install harbor`, then capture verbatim into
`.fleet-goal/evidence/M2/harbor-cli-surface.md`: `harbor --help`,
`harbor run --help`, and (if present) the tasks/dataset listing subcommand
help. Note the exact flags for: dataset selection, single-task filtering,
agent import path, output/jobs directory, and where per-task results (JSON)
and logs land. THE CLIENT CODE MUST MATCH THIS CAPTURED SURFACE — do not
invent flags. If a needed surface does not exist (e.g. no task-list
subcommand), document it in the evidence file and implement the documented
fallback below.

## Deliverable

`engines/harbor_cli.py` — `class HarborCliClient` implementing
`HarborProtocol` for the WU-4 adapter:

- `__init__(self, *, harbor_bin="harbor", dataset="terminal-bench/terminal-bench-2",
  jobs_dir=None, tasks=None, agent_import_path=None, model=None)`.
- `list_tasks(suite)`: use the real listing surface captured in Step 1 if one
  exists; otherwise return the constructor-injected `tasks` tuple and raise a
  clear `ValueError` when `tasks` is None (documented fallback — honest,
  never a hardcoded fake list).
- `run_task(task_id, agent_cmd, timeout_sec)`: invoke the real harbor CLI as
  a subprocess for exactly that task with `stdin=subprocess.DEVNULL`,
  `start_new_session=True`; on timeout kill the WHOLE process group
  (SIGTERM → grace → SIGKILL, mirror `arc_agi3._kill`) and return
  `HarborTaskResult(passed=False, timed_out=True, log_path=<jobs dir>)` —
  killed runs are reported honestly, never dropped, never raised through.
- Parse harbor's on-disk result artifacts for the task: `passed` from the
  verifier outcome; `log_path` = the task's log/artifact path;
  `cost_dollar` = the measured cost IF harbor reports one in its result
  JSON, else `None` (the adapter's declared-budget fallback then sets
  `cost_is_measured=False` — P2 measured-cost honesty; NEVER fabricate).
- Missing harbor binary → raise `FileNotFoundError` with an actionable
  message (`uv tool install harbor`) at construction or first call —
  documented, tested.
- `measure_cmd.py`: add engine choice `harbor-cli` following the WU-7
  `local-arc` pattern (constructs `Tb2HarborAdapter(HarborCliClient(...))`);
  binary-missing surfaces the FileNotFoundError message cleanly, not a
  traceback.

## Tests (hermetic, stub harbor binary on PATH)

- Happy path: stub emits real-shaped result artifacts; 2 tasks 1 pass →
  HarborTaskResult fields exact; adapter integration → quality=0.5.
- Timeout: stub sleeps past timeout_sec, spawns a child (grandchild leak
  probe); assert timed_out=True, passed=False, AND the process group is gone.
- Cost: stub with per-task cost in result JSON → cost_dollar propagated;
  stub without → cost_dollar None → adapter sets cost_is_measured=False.
- Binary missing: actionable FileNotFoundError.
- list_tasks fallback: injected tasks returned; None → ValueError.
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
- `.fleet-goal/evidence/M2/harbor-cli-surface.md` exists with verbatim help
  captures.

## Return contract (four fields ONLY)

1. What was learned (incl. any real-CLI surface surprises)
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
