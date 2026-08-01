---
title: docs/reviews/PR_710_DIGEST.md
status: active
owner: jules
created: 2026-07-28
updated: 2026-07-28
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# PR 710 Digest

## Summary
Formalizes the openbox bridges contract, resolving DEFERRED.md tasks (like OPENBOX-BRIDGES-WIRING and AS17-N2). It introduces a `Binding` abstraction for backend base URLs, wires it to `_dispatch_bridges`, and resolves uncaught `PermissionError` paths in `openbox` credential parsing.

## Findings

```yaml
reviewer_finding:
  kind: architecture
  priority: P3
  blocking_verdict: false
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "def load_bindings(path: Path) -> dict[str, Binding]:"
  fix_suggestion: "LGTM. Properly closes the openbox loopback issue by passing base_url."
  withdraw_condition: "N/A"
  citation: "SEARCH.json idx:run_cmd.py"
```
