---
title: PR 721 Digest
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
This PR bumps the `mcp` dependency from `1.27.2` to `1.28.1` and bumps `cryptography` from `49.0.0` to `50.0.0`. It updates `pyproject.toml` files in `agentdex_arena`, `agentdex_cli`, `kaos`, etc., as well as the `uv.lock` file. As a dependency update, it qualifies for the sync-PR bypass.

```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: uv.lock
evidence_quote: |
  name = "mcp"
  -version = "1.27.2"
  +version = "1.28.1"
fix_suggestion: |
  The PR bumps standard dependencies (`mcp`, `cryptography`) in `pyproject.toml` and updates the lock file. As a routine dependency bump PR (e.g. `chore(deps)`), it passes without requiring detailed behavioral review.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 721."
citation: "SEARCH.json idx:uv.lock"
```
