---
title: M2 P3 candidate glob and name hardening capsule
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
  - The capsule requests fail-closed validation for empty mutable sets and invisible names.
---

# M2 P3: AgentCandidate glob/name hardening

You are an execute-tier coding worker in `/home/admin/gh/agentdex-cli-redesign` on branch `redesign/evolution-market`.

Hard routing contract from the operator: product code edits may be made by you, via this `model_route.sh execute` dispatch. The coordinator will review/test/commit/push. Do **not** commit or push.

## Problem
`packages/adx_frontier/src/adx_frontier/candidate.py` still allows two bad candidate manifests through the pre-run gate:

1. Empty/typo mutable globs can expand to zero files and pass silently, defeating the `weco --sources` pre-run validation contract.
2. Candidate names containing zero-width/invisible Unicode format characters (for example U+200B ZERO WIDTH SPACE) pass as non-empty names.

## Required behavior
- Reject `mutable: []` / missing-or-empty mutable list during `validate()` with `CandidateValidationError`.
- Reject any mutable glob pattern that matches zero concrete in-root files. The error should name the offending pattern so typos are actionable.
- Preserve existing rejection for blank string patterns, absolute patterns, parent escapes, symlink escapes, oversized file sets, etc.
- Reject candidate `name` values containing zero-width/invisible Unicode format characters. At minimum reject U+200B; a general `unicodedata.category(ch) == "Cf"` check is acceptable.
- Add focused tests in `packages/adx_frontier/tests/test_candidate.py` proving these fail on old code and pass after the fix.

## Focused test

```bash
uv run pytest packages/adx_frontier/tests/test_candidate.py
```

## Output
Report files changed, tests run/result, caveats.
