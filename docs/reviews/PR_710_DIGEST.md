---
title: PR 710 Digest
status: active
owner: edwardtang
created: 2026-07-24
updated: 2026-07-24
type: reference
scope: agentdex_cli
---

# PR 710 Digest

**Summary:** Implements the `openbox<->bridges` contract to correctly record the *served* model, rather than just the *requested* pool name. Fixes a bug where substituting a model (e.g., serving a request for `claude-opus` using `deepseek-v4-flash`) would corrupt the ledger attribution.

```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  +    p.add_argument("--json", action="store_true", help="also emit a one-line JSON summary")
fix_suggestion: |
  LGTM - The implementation aligns exactly with the DEFERRED tracking issue and provides an extensive test suite verifying the gate behaviors, including resolving the unmetered zero-cost issue.
withdraw_condition: |
  n/a
citation: SEARCH.json idx:710
```
