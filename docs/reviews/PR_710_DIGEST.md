---
title: "PR 710 Digest"
date: "2026-07-21"
status: "active"
owner: "@jules"
created: "2026-07-21"
updated: "2026-07-21"
type: "reference"
scope: "packages/agentdex_cli"
layer: "service"
verifiable_claims: []
invariants: []
---
# PR 710 Digest

## Summary
Formalizes the openbox-bridges contract (#706). Replaces hardcoded dispatch endpoints with per-backend `base_url` routing. Prevents mismatched models from polluting the ledger (quarantine), and enforces loopback connectivity to block untrusted gateways.

## Findings

```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  AS17-LEDGER-DURABILITY
fix_suggestion: "The seed ledger (FrontierSeedLedger) claims to be append-only but lacks fsync() and advisory locking on write, raising risks for concurrent runners."
withdraw_condition: "Fixed when ledger writes apply proper file-locking and sync guarantees."
citation: "SEARCH.json idx:AS17-LEDGER-DURABILITY"
```

```reviewer_finding
kind: security
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  AS17-INTERVIEW-UNSCANNED
fix_suggestion: "adx interview prompts with bare input() rather than getpass() and performs no credential scanning, leaving users vulnerable to terminal scrollback leaks."
withdraw_condition: "Fixed by sanitizing terminal input."
citation: "SEARCH.json idx:AS17-INTERVIEW-UNSCANNED"
```
