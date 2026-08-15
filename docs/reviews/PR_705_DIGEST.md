---
title: PR 705 Digest
status: draft
owner: jules
created: 2026-07-20
updated: 2026-07-20
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# PR 705: fix(lint): fix UP038 lint errors from PR 704

This PR fixes `UP038` lint errors by replacing `isinstance(x, (A, B))` with `isinstance(x, A | B)`.

```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/adx_frontier/src/adx_frontier/gates.py
evidence_quote: |
  isinstance(x, A | B)
fix_suggestion: |
  The fix correctly applies the new Python 3.10+ Union syntax in `isinstance` checks, resolving ruff UP038 lint errors as intended.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 705."
citation: "SEARCH.json idx:packages/adx_frontier/src/adx_frontier/gates.py"
```

```reviewer_finding
kind: security
priority: P2
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
evidence_quote: |
  except (FileNotFoundError, ValueError, OpenboxError, PermissionError)
fix_suggestion: |
  The PR resolves security/credential path bugs related to `PermissionError` (AS17-N2). The fix correctly catches OS errors in the credential path, fixing the exception escapes while keeping the regression test coverage updated.
withdraw_condition: "This finding acts as an approval for the security checks."
citation: "SEARCH.json idx:packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py"
```
