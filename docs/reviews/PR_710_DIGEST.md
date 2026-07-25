---
title: "PR 710 Digest"
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
# PR 710 Digest

## Summary
Implements the openbox-bridges contract (#706), replacing hardcoded dispatch endpoints with per-backend routing, adding missing loopback connectivity checks, and fixing uncaught PermissionError escapes. Documents AI-Scientist-v2 deep-review findings.

## Findings

```reviewer_finding
kind: security
priority: P1
blocking_verdict: REJECT
exploitability: HIGH
file: DEFERRED.md
evidence_quote: |
  AS17-DENYLIST-GAPS ... Disclosed SECRET_RE misses ... short Basic credentials
fix_suggestion: Address the identified regex gaps to catch all basic credentials.
withdraw_condition: The gaps in SECRET_RE are patched.
citation: SEARCH.json idx:AS17-DENYLIST-GAPS
```

```reviewer_finding
kind: logic
priority: P1
blocking_verdict: REJECT
exploitability: SAFE
file: DEFERRED.md
evidence_quote: |
  AS17-N1 ... The empty-path scanner hole was LIVE ... The in-code comment at openbox_cmd.py:159-164 continues to assert 'Not currently reachable'.
fix_suggestion: Update the comment in openbox_cmd.py to reflect it is reachable, or patch the empty-path scanner hole.
withdraw_condition: The hole is patched or comment updated.
citation: SEARCH.json idx:AS17-N1
```

```reviewer_finding
kind: architecture
priority: P2
blocking_verdict: REJECT
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  Second structural degeneracy: unmetered models cost exactly $0 and are classified as MEASURED.
fix_suggestion: Update `_cost_dollar_and_kind` to correctly classify unmetered models and not consider them as measured to fix the dominance issue.
withdraw_condition: Unmetered models are not classified as measured.
citation: SEARCH.json idx:AS17-N3
```
