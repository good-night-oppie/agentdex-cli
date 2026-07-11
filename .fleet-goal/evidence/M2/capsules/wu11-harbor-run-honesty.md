---
title: "M2 WU-11 fix capsule — harbor run-honesty: infra-failure ≠ measured-0, and process-group kill on any non-timeout exception"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "A harbor run that FAILED infra-side (nonzero exit or no verifier trial-result) MUST be recorded as errored/degraded and MUST NOT be presented as a genuine measured quality=0; and the child process group MUST be reaped on ANY exception during wait, not only TimeoutExpired"
    test: "packages/adx_ladders/tests/test_harbor_cli_client.py + test_tb2_harbor_adapter.py (regressions land with this fix)"
---

# M2 WU-11 — harbor run honesty (re-audit P2 #9 + P2 #6)

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `.fleet-goal/evidence/M2/audit-summary-round2.md` (P2 #9 + #6),
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`
(`run_task` ~91-208, `_parse_job_result`, `HarborTaskResult` import),
`packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py`
(`HarborTaskResult` dataclass ~53-65, `measure` loop ~100-193 — the
`all_costs_measured` + `cost_is_measured` honesty pattern is your model).

## Findings

### P2 #9 — infra-failure silently reported as genuine quality=0
`harbor_cli.py:run_task` returns `passed=False, cost_dollar=None` for BOTH a
real reward-0 run AND an infra failure (harbor nonzero exit, or no
verifier-written trial `result.json`). The tb2 adapter then counts it as a
legitimate failed task in `pass_rate`. An infra flake thus scores as a real
measurement — corrupting the Pareto frontier (same honesty-of-measurement
class as the WU-10 P1, different path).

### P2 #6 — process-group leak on non-timeout exception
`run_task` only calls `_kill(proc)` inside `except subprocess.TimeoutExpired`.
Any OTHER exception during `proc.wait()` (e.g. `KeyboardInterrupt`) leaves the
detached child process group running.

## Guardrails (hard)

- Touch ONLY:
  `packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py`,
  `packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`,
  `packages/adx_ladders/tests/test_harbor_cli_client.py`,
  `packages/adx_ladders/tests/test_tb2_harbor_adapter.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM / NO real harbor runs
  (hermetic stub tests only).
- Preserve ALL existing honest semantics (budget-kill quality=0, measured-cost
  rules, self_reported receipts). This TIGHTENS honesty; it must not loosen it.

## Fix — P2 #6 (do this first, it's small)

In `run_task`, reap on any exception during wait:
```python
try:
    proc.wait(timeout=max(float(timeout_sec), 0.0))
except subprocess.TimeoutExpired:
    timed_out = True
    self._kill(proc)
except BaseException:
    self._kill(proc)      # KeyboardInterrupt / anything → never leak the group
    raise
```
Keep the `finally: log_fh.close()`. Regression: a stub that makes `wait`
raise (monkeypatch `proc.wait` to raise KeyboardInterrupt, or a stub the
test interrupts) → assert `_kill` ran (process group gone) and the exception
propagates.

## Fix — P2 #9 (errored ≠ measured-0)

1. `HarborTaskResult` (in `tb2_harbor.py`): add `errored: bool = False`.
2. `harbor_cli.py`: capture the harbor process returncode. Set
   `errored=True` when `proc.returncode != 0` OR `_find_trial_result`
   returns None (no verifier trial result). A timed-out run keeps
   `timed_out=True` (already honest) and is NOT additionally marked errored
   (distinct failure classes). Genuine parsed reward-0 stays
   `errored=False, passed=False`.
3. `Tb2HarborAdapter.measure`: record per-task `errored` in each task-record
   dict and in the run-summary JSON. Aggregate `errored_count`. Honesty
   rules (all MUST hold):
   - If `errored_count > 0` the run is DEGRADED: set `cost_is_measured=False`
     (an errored run cannot claim measured cost) and add
     `errored_count` + `n_tasks` to the run-summary JSON and to the
     MeasureResult (surface via the summary artifact; do NOT invent a new
     scores axis — keep the 3 frontier axes exact).
   - Errored tasks are EXCLUDED from the `pass_rate` denominator (they are
     "no data", not failures) — but if that would make the denominator zero,
     `quality=0.0` and the run is fully degraded. Document this in the
     `measure` docstring.
   - The self_reported receipt still lists artifacts; a degraded run is still
     honestly recorded, never dropped.
4. Update the module docstring's Scores section to state the errored/degraded
   semantics.

## Tests

- P2 #6: non-timeout exception during wait → `_kill` invoked, group reaped,
  exception re-raised.
- P2 #9 infra-fail: stub harbor exits nonzero with NO trial result → adapter
  MeasureResult has `errored_count>=1`, `cost_is_measured=False`, and the
  task is excluded from pass_rate (assert quality reflects only real tasks).
- P2 #9 mixed: 3 tasks, 1 pass / 1 genuine reward-0 / 1 errored → quality =
  1/2 (errored excluded), errored_count=1, cost_is_measured=False.
- Regression guard: a CLEAN all-measured run still reports
  `cost_is_measured=True`, `errored_count=0` (no honesty regression).
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
