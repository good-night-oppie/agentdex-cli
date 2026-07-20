---
title: "PR 710 Digest"
date: "2026-07-20"
status: "active"
owner: "@jules"
created: "2026-07-20"
updated: "2026-07-20"
type: "reference"
scope: "packages/agentdex_cli"
layer: "service"
verifiable_claims: []
invariants: []
---
# PR 710 Digest

## Summary
Implements the openbox-bridges contract (#706). Resolves substitution errors, enforces loopback base_url, quarantines mismatch candidates, and fixes unhandled PermissionError escapes.

## Findings

```reviewer_finding
kind: security
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  AS17-INTERVIEW-UNSCANNED
fix_suggestion: "adx interview scans nothing... prompts with bare input() for all six questions. Use getpass to prompt for sensitive information, or document that input is not sanitized against secrets."
withdraw_condition: "Fixed by sanitizing input or documenting the risk."
citation: "SEARCH.json idx:AS17-INTERVIEW-UNSCANNED"
```

```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  AS17-LEDGER-DURABILITY
fix_suggestion: "Seed ledger provides fewer guarantees than 'append-only ledger' implies: no fsync, no advisory lock, no per-row checksum. Add missing test coverage and fix durability."
withdraw_condition: "Fixed by adding tests and fixing ledger durability."
citation: "SEARCH.json idx:AS17-LEDGER-DURABILITY"
```
