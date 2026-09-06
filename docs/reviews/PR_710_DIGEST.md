---
title: PR 710 Digest
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
This PR formalizes the `openbox<->bridges` contract by integrating `.agentdex/openbox.yaml` into the `run_cmd` and `openbox_cmd` modules, resolving issue #706. It ensures that when using `--engine bridges`, the CLI actually parses backend configurations (e.g. `base_url`) rather than relying on a hardcoded loopback gateway. It adds extensive tests (`test_openbox_bridges_contract.py`) to verify real HTTP bindings.

```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  def _dispatch_bridges(
fix_suggestion: |
  The PR successfully formalizes the contract between `openbox` and `bridges`, properly reading base URLs and tokens from `openbox.yaml` for routing. It properly handles configuration and prevents unauthenticated API access, which closes issue #706.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 710."
citation: "SEARCH.json idx:packages/agentdex_cli/src/agentdex_cli/run_cmd.py"
```
