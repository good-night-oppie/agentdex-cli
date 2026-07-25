---
title: "PR 705 Digest"
status: active
owner: "@jules"
created: "2026-07-24"
updated: "2026-07-24"
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
verifiable_claims: []
invariants: []
---
# PR 705 Digest

## Summary
Fixes `UP038` lint errors (using `|` instead of tuples with `isinstance`) across the codebase. Also modifies test suite and openbox logic, and fixes bug for NaN qualities and unhandled edge cases.

## Findings

```reviewer_finding
kind: security
priority: P1
blocking_verdict: REJECT
exploitability: SAFE
file: packages/agentdex_cli/tests/test_run_cmd.py
evidence_quote: |
  _FAKE_SK = "sk-TESTFAKEabcdefghijklmnop"  # pragma: allowlist secret
fix_suggestion: Append ` # pragma: allowlist secret` to the hardcoded secret to prevent detect-secrets from flagging it in tests.
withdraw_condition: The `pragma: allowlist secret` is appended or the credential is removed.
citation: SEARCH.json idx:test_run_cmd.py
```

```reviewer_finding
kind: security
priority: P1
blocking_verdict: REJECT
exploitability: SAFE
file: packages/agentdex_cli/tests/test_openbox_cmd.py
evidence_quote: |
  secret = "sk-abcdefghijklmnopqrstuvwxyz"  # pragma: allowlist secret
fix_suggestion: Append ` # pragma: allowlist secret` to the hardcoded secret to prevent detect-secrets from flagging it.
withdraw_condition: The `pragma: allowlist secret` is appended or the credential is removed.
citation: SEARCH.json idx:test_openbox_cmd.py
```

```reviewer_finding
kind: logic
priority: P2
blocking_verdict: REJECT
exploitability: SAFE
file: sweeps/adx-cli-fleet-kanban.json
evidence_quote: |
  arena_tui UP038 fixed #283
fix_suggestion: Confirm if the PR title matches the changes since sweeps/adx-cli-fleet-kanban.json has nothing to do with UP038.
withdraw_condition: Clarified why sweeps is updated.
citation: SEARCH.json idx:sweeps/adx-cli-fleet-kanban.json
```
