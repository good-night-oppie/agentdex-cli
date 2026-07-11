---
title: M2 P3 registry known ladders bidirectional capsule
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
  - The capsule requests equality between registry ladder ids and KNOWN_LADDERS.
---

# M2 P3: registry ↔ KNOWN_LADDERS bidirectional consistency

You are an execute-tier coding worker in `/home/admin/gh/agentdex-cli-redesign` on branch `redesign/evolution-market`.

Hard routing contract from the operator: product code edits may be made by you, via this `model_route.sh execute` dispatch. The coordinator will review/test/commit/push. Do **not** commit or push.

## Problem
`packages/adx_ladders/tests/test_registry.py::test_known_ladders_consistency` is one-directional: registry must be a superset of `adx_frontier.candidate.KNOWN_LADDERS`. It should assert set equality both ways so stale registry-only ladders or candidate-only ladders fail.

## Required behavior
- Update the test so it checks exact equality between packaged registry ladder ids and `KNOWN_LADDERS`.
- Preserve a clear failure message that names both missing-from-registry and extra-in-registry when equality fails.
- Do not change product runtime code unless needed for the test to pass.

## Focused test

```bash
uv run pytest packages/adx_ladders/tests/test_registry.py
```

## Output
Report files changed, tests run/result, caveats.
