---
title: "M2 WU-3 request capsule — arc_agi3 run-adapter (out-of-process, fakes in unit tests)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "The adapter MUST execute the candidate out-of-process (subprocess of candidate.entrypoint) and MUST emit MeasureResult with scores keyed exactly FRONTIER_AXES and a Receipt per D6 (verified=>arc_scorecard_id ref; self_reported=>raw artifacts)"
    test: "packages/adx_ladders/tests/test_arc_agi3_adapter.py (lands with this WU)"
---

# M2 WU-3 — `arc_agi3` run-adapter

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `packages/adx_ladders/src/adx_ladders/base.py` (WU-2 contract —
subclass `LadderAdapter`, consume `MeasureResult`/`Receipt`/`LadderClass`),
`packages/adx_frontier/src/adx_frontier/candidate.py` (WU-1),
`.fleet-goal/evidence/M1/DESIGN.md` (loop diagram + two-tier trust), ADR-0015
D3/D5/D6.

## Guardrails (hard)

- Touch ONLY `packages/adx_ladders/src/adx_ladders/adapters/**` (new subpackage)
  and `packages/adx_ladders/tests/**` (new test file(s)). NOTHING else — no
  root pyproject churn (adapters live inside the existing package).
- Do NOT `git commit` / `git push`.
- NO network calls in code paths exercised by unit tests; the hosted-API
  receipt path is behind an injected client interface, faked in tests. Do not
  install the `arc-agi` package in this WU (integration comes later); code
  against a thin `ArcEngineProtocol` you define.

## Deliverable

`adapters/__init__.py` + `adapters/arc_agi3.py`:

- `class ArcAgi3Adapter(LadderAdapter)`: `ladder_id = "arc-agi-3"`,
  `ladder_class = LadderClass.LIVE_ADVERSARIAL`.
- **Out-of-process candidate execution:** the candidate's `entrypoint` runs as
  a subprocess speaking a line-delimited JSON stdio protocol you define in the
  module docstring: adapter → `{"type":"observation", "game":..., "frame":...}`;
  candidate → `{"type":"action", "action":...}`. Wall-clock enforced with the
  candidate's declared `budget.wall_clock_min` (kill on exceed → that run
  scores quality=0 and is still reported honestly, not dropped).
- `measure(candidate)` orchestrates: `pre_run_check` → episodes via an
  injected `engine: ArcEngineProtocol` (methods `reset(game_id)`,
  `step(action)`, `score()`, `scorecard_id() -> str | None`) → aggregates →
  `MeasureResult` with scores exactly
  `{"quality": <engine score 0..1>, "cost_dollar": <measured or declared>,
  "wall_clock_sec": <measured>}`.
- **Receipt (D6):** if `scorecard_id()` returns an id (hosted/verified path) →
  `Receipt(tier="verified", kind="arc_scorecard_id", ref=<id>)`; else →
  `Receipt(tier="self_reported", kind="raw_artifacts", artifacts=(<run log
  path written under the candidate dir /.adx/runs/...>,))` — the artifact file
  must actually be written (JSON: episodes, actions count, scores, timing).

## Tests (`tests/test_arc_agi3_adapter.py`) — all with fakes, no network

- Fake engine + a tiny fake candidate entrypoint (a python one-liner script
  written to tmp_path that echoes valid action JSON): measure() returns
  MeasureResult; axes keys exact; wall_clock_sec > 0.
- Verified path: fake engine returns scorecard id → Receipt tier=verified.
- Self-reported path: no scorecard id → artifacts file exists on disk, tier
  correct.
- Budget kill: entrypoint that sleeps past a tiny wall_clock budget → run
  reported with quality=0, not an exception.
- pre_run_check rejection: candidate without "arc-agi-3" in ladders rejects.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ -q` (all, incl. WU-2's 16, green)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
