---
title: PR 710 Digest
status: active
owner: jules
created: 2026-08-16
updated: 2026-08-16
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# PR 710: feat(cli,openbox): formalize the openbox<->bridges contract (#706)

## Summary
This PR formalizes the contract between the `openbox` and `bridges` components. It adds the ability to load bindings from YAML and mock them using the CLI, which includes parsing logic, backend validation, and test adjustments.

## Checks
- **Correctness:** The logic for resolving base URLs and parsing document structures is implemented securely with appropriate exceptions thrown for invalid backends.
- **Security:** No hardcoded credentials. It introduces loopback binding logic but does so safely. Tests verify security logic (e.g. `test_non_loopback_base_url_is_rejected_naming_the_backend`). Secret-detection regexes in the codebase are intact.
- **Test Coverage:** Extensive testing is provided for the new features, including `test_openbox_bridges_contract.py` which verifies substitution, serialization, and integration.


```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
evidence_quote: def load_bindings(path: Path) -> dict[str, Binding]:
fix_suggestion: The PR establishes the openbox to bridges contract correctly. Tests were added. This serves as an approval since logic appears sound.
withdraw_condition: Approving as feature is complete.
citation: SEARCH.json idx:packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
```
