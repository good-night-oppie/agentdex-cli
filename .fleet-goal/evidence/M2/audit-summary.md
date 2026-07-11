---
title: "M2 audit + code-review summary (fresh clean-context, wf_a973b1de-359)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The three P1 gate bypasses (non-finite budget, stdin-deadlock budget-kill defeat, process-group leak) are closed and regression-tested before M2 closure"
    test: "packages/adx_frontier/tests/test_candidate.py + packages/adx_ladders/tests/test_arc_agi3_adapter.py + packages/agentdex_cli/tests/test_measure_cmd.py (WU-6)"
---

execution_route: mroute orchestrate (fable-5 tier) — Workflow wf_a973b1de-359, 2 fresh clean-context subagents (5q audit + adversarial code review) + 3 adversarial verifiers, read-only

# EDITH agentdex-redesign M2 — audit + review summary

## Verdict: AUDIT_M2_PASS (milestone honesty) + CODE_REVIEW_M2_FAIL (3 P1 bypasses) → M2 STAYS OPEN

The 5-question audit PASSED on milestone honesty (state files make no
false-completion claim; fakes are hard-fenced; the pre-run gate fires; 44/44
tests pass; all 5 spikes have substantive evidence) and concluded **M2 may NOT
close now** — fake-engine runs are proxies, not "measured runs on both
adapters" under the standing principle, so real-engine WUs + real measured
runs + this review are still required.

The adversarial code review returned **FAIL**: three P1 gate bypasses exist in
the LANDED M2 code (not the queued WUs), all reproduced concretely by
independent verifiers (confirmed_blocking, zero refuted).

## Confirmed P1 bypasses (must fix before real-engine WUs)

1. **NaN/Inf budget bypasses the pre-run gate.** `candidate.py:79` uses
   `budget.usd <= 0 or wall_clock_min <= 0`; NaN/Inf make both False, so
   `budget: {usd: .nan, wall_clock_min: .nan}` passes `validate()` +
   `pre_run_check`, and `adx measure` returns exit 0 serializing invalid
   `NaN` JSON tokens (RFC-8259 violation → downstream ledger/website
   JSON.parse fails). Also the wall-clock kill can never fire on a NaN/Inf
   deadline. Fix: `math.isfinite` guard in `validate()` + `allow_nan=False`
   in the CLI serialize.
2. **Budget kill defeated by stdin write deadlock.** `arc_agi3.py:252`
   `proc.stdin.write/flush` has no timeout; a frame > pipe buffer (~64KB)
   with a candidate that never reads stdin blocks the parent, so the deadline
   check never runs (reproduced: >8s under a 0.05s budget, hung). Fix: bound
   the write (select-on-writability against remaining deadline, or writer
   thread w/ timeout) → timed-out result.
3. **Budget kill signals only the direct child.** `arc_agi3.py:171` Popen
   without `start_new_session=True`; `_kill` SIGKILLs only `proc`, so
   candidate-spawned grandchildren survive and keep spending the user's BYO
   compute after the "kill" (reproduced). Fix: `start_new_session=True` +
   `os.killpg(os.getpgid(proc.pid), SIGKILL)` with SIGTERM→SIGKILL escalation.

## P2 (fold into the same fix WU — same "ungameable gate" theme)

- Read-only candidate dir → unhandled `PermissionError` crashes `measure()`,
  dropping the result/receipt (contradicts "honest, not dropped").
- Mutable globs escape root (`../`, out-of-root symlinks not confined);
  absolute glob raises `NotImplementedError`, out-of-root oversize raises
  `ValueError` from `relative_to` — raw exceptions crash the CLI instead of a
  clean exit-2 gate rejection.
- `MeasureResult` score VALUES unvalidated (accepts `'eleven'`/None/NaN) and
  the scores dict is mutable post-construction in a frozen dataclass.
- Verified `Receipt` accepts whitespace-only `ref`; self_reported accepts
  blank artifact strings.
- cost_dollar axis degenerates to the DECLARED budget when engines report no
  measured cost — a proxy on an axis the principle says must be real; the
  real-engine WUs MUST require measured cost or relabel the axis budget_usd.

## P3 (hygiene)

- registry↔KNOWN_LADDERS consistency test is one-directional (superset only).
- empty/typo mutable glob passes silently; zero-width-space name accepted.
- `registry.yaml` swe-bench-pro note "Fourth-adapter slot TBD" is stale vs the
  spike-2 decision.
- PokeAgent organizer ToS ask + BYO-differential residual lack a DEFERRED.md
  row with Until date.

## Supporting evidence

- Workflow wf_a973b1de-359: audit PASS, review FAIL, 3/3 blocking CONFIRMED by
  independent verifiers, 0 refuted; 44/44 M2 tests pass (625 across installed
  packages; 51 arena collection errors + 1 kaos failure are pre-existing
  env issues, not M2 regressions).
- Journal: subagents/workflows/wf_a973b1de-359/journal.jsonl.

## What should happen next

Fix WU (via mroute execute) closing the 3 P1s + the gate-integrity P2s, with
regression tests per bug; then real-engine integration WUs (with measured-cost
acceptance criteria); then real measured runs filed under evidence/M2/; then a
re-audit. M2 does not close until all of that lands.

AUDIT_M2_PASS
CODE_REVIEW_M2_FAIL
