---
title: M2 P2 measured-cost honesty capsule
status: active
owner: harness-41
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: M2
layer: cross-cutting
cross_cutting: true
verifiable_claims:
  - Product-code edits are dispatched through model_route execute.
  - The capsule requests cost_is_measured metadata without changing frontier axes.
---

# M2 P2: measured-cost honesty (coding task)

You are an execute-tier coding worker in `/home/admin/gh/agentdex-cli-redesign` on branch `redesign/evolution-market`.

Hard routing contract from the operator: product code edits may be made by you, via this `model_route.sh execute` dispatch. The coordinator will review/test/commit/push. Do **not** commit or push.

## Problem
Audit finding: `cost_dollar` degenerates to declared budget when the adapter/engine reports no measured spend. This makes the Pareto frontier able to treat a declared budget as real spend.

Known sites:
- `packages/adx_ladders/src/adx_ladders/base.py` `MeasureResult`
- `packages/adx_ladders/src/adx_ladders/adapters/arc_agi3.py` around cost fallback
- `packages/adx_ladders/src/adx_ladders/adapters/tb2_harbor.py` around cost fallback
- `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py` serializer
- relevant tests under `packages/adx_ladders/tests/` and `packages/agentdex_cli/tests/test_measure_cmd.py`

## Required behavior
1. Add explicit measured-cost honesty to `MeasureResult`, e.g. a boolean `cost_is_measured` field (default should be chosen to avoid accidental false honesty; prefer explicit at call sites if practical).
2. When ARC has no measured/explicit cost from the engine/client and falls back to `candidate.budget.usd`, the result must carry `cost_is_measured=False`.
3. When TB2 has at least one task without `HarborTaskResult.cost_dollar` and falls back to `candidate.budget.usd`, the result must carry `cost_is_measured=False`.
4. When TB2 all tasks report measured costs and the adapter sums them, `cost_is_measured=True`.
5. When adapter constructor `cost_dollar` override is used, treat it as measured and set `cost_is_measured=True` (it is the injected real-client measured cost hook until real clients land).
6. Serialize `cost_is_measured` in `adx measure` JSON output, so downstream frontier/ledger cannot mistake declared budget for measured spend.
7. Include the flag in adapter artifact summaries/log JSON where scores are written, so receipts preserve the honesty bit.
8. Keep existing score axes exactly `quality`, `cost_dollar`, `wall_clock_sec`; do not add a fourth frontier axis.
9. Add/adjust tests that fail on the current code and pass after the fix.

## Suggested focused tests
Run at least:

```bash
uv run pytest packages/adx_ladders/tests/test_base.py packages/adx_ladders/tests/test_arc_agi3_adapter.py packages/adx_ladders/tests/test_tb2_harbor_adapter.py packages/agentdex_cli/tests/test_measure_cmd.py
```

## Output
At the end, report:
- files changed
- tests run and result
- any caveats
