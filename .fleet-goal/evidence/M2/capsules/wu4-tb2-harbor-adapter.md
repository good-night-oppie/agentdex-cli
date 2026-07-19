---
title: "M2 WU-4 request capsule — tb2_harbor run-adapter (static class, out-of-process, fakes in unit tests)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The tb2 adapter MUST execute Harbor out-of-process behind an injected HarborProtocol, MUST report budget-killed runs honestly (quality=0, never dropped), and MUST emit self_reported Receipts with on-disk raw artifacts (static-class lane; no third-party receipt authority)"
    test: "packages/adx_ladders/tests/test_tb2_harbor_adapter.py (lands with this WU)"
---

# M2 WU-4 — `tb2_harbor` run-adapter

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `packages/adx_ladders/src/adx_ladders/adapters/arc_agi3.py`
(WU-3 — mirror its structure/idioms exactly: injected protocol, subprocess
budget kill, receipt writing), `base.py` (contract), `candidate.py` (WU-1),
ADR-0015 D3/D4/D5/D6.

## Guardrails (hard)

- Touch ONLY `packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py`
  (new) + `adapters/__init__.py` (export) +
  `packages/adx_ladders/tests/test_tb2_harbor_adapter.py` (new). NOTHING else.
- Do NOT `git commit` / `git push`.
- NO network / NO `uv tool install harbor` in this WU — code against a thin
  `HarborProtocol` you define (methods: `run_task(task_id, agent_cmd,
  timeout_sec) -> HarborTaskResult(passed: bool, log_path: str)`,
  `list_tasks(suite) -> list[str]`); faked in tests. Real Harbor integration
  is a later WU.

## Deliverable

`adapters/tb2_harbor.py`:

- `class Tb2HarborAdapter(LadderAdapter)`: `ladder_id = "tb2"`,
  `ladder_class = LadderClass.STATIC`.
- `measure(candidate)`: `pre_run_check` → run the suite's tasks via the
  injected `HarborProtocol`, passing `candidate.entrypoint` as the agent
  command, dividing the candidate's declared `budget.wall_clock_min` across
  tasks as per-task timeouts (document the division rule in the docstring —
  simple equal split is fine for v1; a task exceeding its slice is killed by
  the protocol and counts as failed, reported honestly, never dropped).
- Scores exactly `{"quality": pass_rate 0..1, "cost_dollar": <measured if the
  protocol reports it, else the declared budget.usd — document which>,
  "wall_clock_sec": <measured>}`.
- **Receipt (D6, static lane):** ALWAYS
  `Receipt(tier="self_reported", kind="raw_artifacts", artifacts=(<run
  summary JSON written under candidate dir .adx/runs/...>, <harbor log paths
  as reported>))` — TB2 has no third-party receipt authority; the summary
  JSON must include per-task pass/fail + timing so M3's held-out /
  decontamination gate (static-class guard) can consume it later.

## Tests (fakes only, no network)

- Happy path: fake protocol, 3 tasks, 2 pass → quality≈0.667, axes keys
  exact, wall_clock_sec > 0, summary JSON exists with per-task records.
- Budget kill: a task the fake reports as timed-out → counted failed,
  MeasureResult still returned.
- Receipt: always self_reported + artifacts non-empty + files exist.
- pre_run_check rejection: candidate without "tb2" in ladders.
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ -q`

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
