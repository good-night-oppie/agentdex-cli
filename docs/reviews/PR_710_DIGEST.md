---
title: "PR 710 Digest"
date: "2026-07-19"
status: "active"
owner: "@jules"
created: "2026-07-19"
updated: "2026-07-19"
type: "reference"
scope: "packages/agentdex_cli"
layer: "service"
verifiable_claims: []
invariants: []
---
# PR 710 Digest

## Summary
Implements the openbox-bridges contract (#706). It resolves substitution errors where the gateway routed pools to different models, preventing fabricated costs and measurement corruption. Enforces loopback base_url and correctly quarantines mismatch candidates. Fixes two unhandled `PermissionError` escapes.

## Findings

```reviewer_finding
kind: security
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  109:            raw = input(f"     [{q.default}] > ").strip()
fix_suggestion: Use `getpass` to prompt for sensitive information, or document that input is not sanitized against secrets.
withdraw_condition: Use `getpass` to prompt for sensitive information, or document that input is not sanitized against secrets.
citation: SEARCH.json idx:123
```

```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  167:    def __init__(self, path: Path, *, max_cost: float | None = None) -> None:
fix_suggestion: Add missing test coverage around Ledger durability which provides fewer guarantees than implied.
withdraw_condition: Add missing test coverage around Ledger durability which provides fewer guarantees than implied.
citation: SEARCH.json idx:123
```
