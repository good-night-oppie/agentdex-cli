---
title: M2 P3 SWE-Bench Pro registry note refresh capsule
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
  - The capsule requests replacing a stale TBD note with the M2 spike decision.
---

# M2 P3: stale registry note for SWE-Bench Pro

You are an execute-tier coding worker in `/home/admin/gh/agentdex-cli-redesign` on branch `redesign/evolution-market`.

Hard routing contract from the operator: product/metadata edits may be made by you, via this `model_route.sh execute` dispatch. The coordinator will review/test/commit/push. Do **not** commit or push.

## Problem
`packages/adx_ladders/src/adx_ladders/registry.yaml` has a stale SWE-Bench Pro note:

> Fourth-adapter slot TBD.

M2 spike-2 decided the fourth adapter slot is SWE-Bench Pro @ N=10.

## Required behavior
- Update the `swe-bench-pro` registry note to remove the stale TBD language.
- Mention the spike decision: SWE-Bench Pro @ N=10 is the fourth-adapter slot / future adapter target.
- Preserve existing static-lane held-out/decontamination wording.
- Run registry tests.

## Focused test

```bash
uv run pytest packages/adx_ladders/tests/test_registry.py
```

## Output
Report files changed, tests run/result, caveats.
