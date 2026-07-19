---
title: "M2 WU-5 request capsule — `adx measure` CLI verb (end-to-end with fake engines)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "`adx measure` MUST refuse to run when the pre-run validation gate rejects (exit 2, gate message verbatim) and MUST emit the MeasureResult as JSON (scores keyed exactly FRONTIER_AXES + receipt tier/kind/ref/artifacts) on success"
    test: "packages/agentdex_cli/tests/test_measure_cmd.py (lands with this WU)"
---

# M2 WU-5 — `adx measure` CLI verb

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `packages/agentdex_cli/` (existing CLI — find how `adx` verbs are
registered and MATCH that pattern exactly), `packages/adx_frontier/src/adx_frontier/candidate.py`,
`packages/adx_ladders/src/adx_ladders/{base.py,registry.py,adapters/}`,
`.fleet-goal/evidence/M1/DESIGN.md` "CLI surface".

## Guardrails (hard)

- Touch ONLY `packages/agentdex_cli/**` (new verb + tests) and, if the CLI
  package needs the new deps, its own `pyproject.toml` (add `adx-frontier`,
  `adx-ladders` workspace deps). NOTHING else.
- Do NOT `git commit` / `git push`. No network.

## Deliverable

`adx measure --agent <dir> --ladder <id> [--out <path>] [--engine-fake]`:

1. `load_candidate(dir)` → `candidate.validate()` via the adapter's
   `pre_run_check`. Gate rejection → print the CandidateValidationError
   message to stderr verbatim, **exit code 2**, run NOTHING.
2. Resolve the adapter by ladder id (v1: `arc-agi-3` → ArcAgi3Adapter,
   `tb2` → Tb2HarborAdapter; a ladder with `run_adapter: false` in the
   registry → clear error, exit 3). Real engine/harbor clients don't exist
   yet: the adapter constructors take the injected protocol — provide a
   `--engine-fake` flag wiring deterministic in-repo fake implementations
   (put them in `agentdex_cli` under a `_fakes.py`, clearly marked
   NOT-FOR-LEADERBOARD: receipts from fakes MUST be forced to
   tier=self_reported with kind="fake_engine" so a fake run can never claim
   a verified receipt) so the end-to-end path is demonstrable today.
3. Success → MeasureResult serialized as JSON to stdout (and `--out` file):
   `{ladder_id, base_model, scores{...FRONTIER_AXES}, receipt{tier,kind,ref,
   artifacts}, budget{usd,wall_clock_min}, measured_at_utc}`.
4. Help text documents the two-class taxonomy + that fake-engine results are
   never leaderboard-eligible.

## Tests (`test_measure_cmd.py`, CliRunner-style per repo convention)

- Gate rejection path: invalid candidate dir → exit 2, message contains
  "narrow your weco-mutable subset" (use an oversized fixture).
- Happy path with --engine-fake on arc-agi-3 AND tb2: exit 0, JSON parses,
  scores keys exact, receipt.kind == "fake_engine", tier == "self_reported".
- Unknown ladder → exit != 0 with clear message; run_adapter:false ladder
  (e.g. kaggle) → exit 3.

## Acceptance (run + paste)

- `uv run pytest packages/agentdex_cli/tests/test_measure_cmd.py packages/adx_ladders/tests/ packages/adx_frontier/tests/ -q`
- One real invocation transcript:
  `uv run adx measure --agent <tmp fixture> --ladder tb2 --engine-fake`

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
