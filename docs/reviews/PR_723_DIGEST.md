---
title: PR 723 Digest
status: active
owner: etang
created: 2026-07-20
updated: 2026-07-20
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

## Summary
This PR bumps `brace-expansion` from `1.1.15` to `1.1.18` in `packages/adx_showdown`. This is a standard `chore(deps)` automated dependency bump and qualifies for the sync-PR bypass rule.

```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/adx_showdown/package-lock.json
evidence_quote: |
  "node_modules/brace-expansion": {
  -      "version": "1.1.15",
  -      "resolved": "https://registry.npmjs.org/brace-expansion/-/brace-expansion-1.1.15.tgz",
  +      "version": "1.1.18",
  +      "resolved": "https://registry.npmjs.org/brace-expansion/-/brace-expansion-1.1.18.tgz",
fix_suggestion: |
  The PR bumps the `brace-expansion` dependency in `packages/adx_showdown/package-lock.json`. As an automated `chore(deps)` PR, it passes the PR cascade breaker bypass rule.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 723."
citation: "SEARCH.json idx:packages/adx_showdown/package-lock.json"
```
