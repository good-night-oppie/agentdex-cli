---
title: PR 710 Digest
status: active
owner: "@EdwardTang"
created: 2026-07-20
updated: 2026-07-20
type: reference
scope: packages/agentdex_cli
layer: service
cross_cutting: false
---

# PR 710: feat(cli,openbox): formalize the openbox<->bridges contract (#706)

**Summary**: This PR formalizes the contract between `openbox` and `bridges`, closing issue #706. It adds an `openbox init` and `openbox check` command, validation for the `openbox.yaml` file, and wiring to the agentdex allocator loop.

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: HIGH
  file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
  evidence_quote: "_scan_strings"
  fix_suggestion: "Ensure that secret scanning is comprehensive and does not have gaps like un-scanned `interview_cmd.py` user input or missing `SECRET_RE` coverage for short tokens."
  withdraw_condition: "Fix the regexes and interview command to scan for secrets."
```

```yaml
reviewer_finding:
  kind: correctness
  priority: P2
  blocking_verdict: false
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "append-only ledger"
  fix_suggestion: "Add fsync and advisory locks to `FrontierSeedLedger.append()` to ensure durability and concurrent safety, as missing these can cause silent row loss."
  withdraw_condition: "Fix ledger write concurrency and persistence."
```

```yaml
reviewer_finding:
  kind: logic
  priority: P2
  blocking_verdict: false
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "cost_dollar_and_kind"
  fix_suggestion: "Ensure unmetered models do not strictly dominate by returning a non-zero or fallback value appropriately."
  withdraw_condition: "Fix unmetered cost dominance logic."
```

```yaml
reviewer_finding:
  kind: correctness
  priority: P2
  blocking_verdict: false
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
  evidence_quote: "_scan_strings"
  fix_suggestion: "Missing test coverage: there are no tests for `interview_cmd.py` scanning. Add test coverage for interview secret-detection."
  withdraw_condition: "Add missing test coverage."
```
