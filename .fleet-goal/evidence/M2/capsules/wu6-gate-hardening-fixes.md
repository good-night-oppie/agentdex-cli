---
title: "M2 WU-6 request capsule — gate-hardening fixes (3 P1 bypasses + gate-integrity P2s)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The pre-run gate MUST reject non-finite (NaN/Inf) budgets, and adx measure MUST NOT emit non-RFC-8259 JSON; the out-of-process budget kill MUST terminate the whole process group within the deadline even under a stdin-write deadlock; measure() MUST return an honest MeasureResult (never crash) on a read-only candidate dir; mutable globs MUST be confined to the candidate root and malformed globs MUST surface as CandidateValidationError not raw exceptions"
    test: "packages/adx_frontier/tests/test_candidate.py + packages/adx_ladders/tests/test_arc_agi3_adapter.py + packages/agentdex_cli/tests/test_measure_cmd.py (regression tests land with this WU, one per bug)"
---

# M2 WU-6 — gate-hardening fixes

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
A fresh adversarial code review (evidence/M2/audit-summary.md) found 3 CONFIRMED
P1 gate bypasses + gate-integrity P2s in the LANDED code. Fix ALL of the
following. READ FIRST: evidence/M2/audit-summary.md (the finding list with exact
file:line + fix direction), then the three source files.

## Guardrails (hard)

- Touch ONLY: `packages/adx_frontier/src/adx_frontier/candidate.py`,
  `packages/adx_ladders/src/adx_ladders/base.py`,
  `packages/adx_ladders/src/adx_ladders/adapters/arc_agi3.py`,
  `packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py`,
  `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`, and the matching
  `tests/` files. NOTHING else.
- Do NOT `git commit` / `git push`. No network. Keep every existing test green.
- Each fix ships with a regression test that FAILS before your change and
  passes after (state which test covers which bug in your return).

## Fixes (all required)

**P1-1 — non-finite budget + non-spec JSON.**
- `candidate.py` `validate()`: reject with CandidateValidationError when
  `budget.usd`/`budget.wall_clock_min` are not finite (`math.isfinite`) or
  not > 0. (NaN and Inf must both reject.)
- `measure_cmd.py`: serialize with `json.dumps(..., allow_nan=False)` so a
  non-finite value can never emit bare `NaN`/`Infinity` tokens; if that raises,
  exit non-zero cleanly (not a traceback).

**P1-2 — stdin write deadlock.** In `arc_agi3.py` (and mirror any equivalent
in `tb2_harbor.py` if it writes to a child), the write to `proc.stdin` MUST be
bounded by the remaining wall-clock deadline: use `select` on writability
against the deadline, or a writer thread joined with a timeout; on exceed,
kill and return a timed-out MeasureResult (quality=0), never hang.

**P1-3 — process-group kill.** Spawn the candidate with
`start_new_session=True`; on budget kill send `os.killpg(os.getpgid(proc.pid),
SIGTERM)` then escalate to `SIGKILL` after a short grace, so grandchildren die
too. Apply to every subprocess spawn in the adapters.

**P2-a — read-only candidate dir.** Writing `.adx/runs/...` must not crash
`measure()`. Either write under a writable base (fall back to a temp dir) or
catch the OSError and degrade to an in-memory self_reported receipt — always
return a MeasureResult ("honest, not dropped").

**P2-b — glob confinement.** `candidate.py` `expand_mutable()`: resolve each
match and DROP (or reject) any path that is not under `root` (out-of-root
symlinks, `../` escapes). Guard absolute-pattern globs and compute the
oversized-file detail WITHOUT `relative_to` on out-of-root paths, so a
malformed `mutable` surfaces as CandidateValidationError (clean exit 2), never
a raw NotImplementedError/ValueError.

**P2-c — MeasureResult value validation + immutability.** `base.py`
`MeasureResult.__post_init__`: require each score value be a finite float;
store the scores as an immutable mapping (e.g. `MappingProxyType` over a
validated copy) so post-construction mutation can't break the axes invariant.

**P2-d — receipt ref/artifact non-blank.** `base.py` `Receipt.__post_init__`:
verified tier requires a non-whitespace `ref` (`.strip()`); self_reported
requires at least one non-blank artifact string.

## Tests (one regression per bug, in the matching test file)

- NaN budget rejected by validate() (+ Inf); `adx measure` on a NaN-budget
  fixture exits non-zero with no `NaN` token in output.
- stdin-deadlock fixture (large frame + non-reading sleeper) returns a
  timed-out MeasureResult within a small budget (assert bounded wall time).
- grandchild fixture: after budget kill, the recorded grandchild pid is dead.
- read-only candidate dir: measure() returns a MeasureResult (no exception).
- out-of-root symlink / `../` glob / absolute glob → CandidateValidationError
  (exit 2 via CLI), not a raw exception.
- MeasureResult rejects non-finite / non-float score value; scores mapping is
  not mutable post-construction.
- Receipt rejects whitespace ref (verified) and blank-only artifacts.

## Acceptance (run + paste)

- `uv run pytest packages/adx_frontier/tests/ packages/adx_ladders/tests/ packages/agentdex_cli/tests/ -q`
- `uv run adx measure` on a NaN-budget /tmp fixture → show it now exits
  non-zero with a clean gate message (no traceback, no NaN token).

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list + which test covers which of P1-1/P1-2/P1-3/P2-a..d)
3. Supporting evidence (test output verbatim + the NaN-fixture transcript)
4. What should happen next
