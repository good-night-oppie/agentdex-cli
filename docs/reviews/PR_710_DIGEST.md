---
title: "PR 710 Digest"
date: "2026-07-28"
status: "active"
owner: "@jules"
created: "2026-07-28"
updated: "2026-07-28"
type: "reference"
scope: "packages/agentdex_cli"
layer: "service"
verifiable_claims: []
invariants: []
---
# PR 710 Digest

## Summary
Review for PR 710: feat(cli,openbox): formalize the openbox<->bridges contract (#706)

## Findings

```reviewer_finding
kind: security
priority: P2
blocking_verdict: DEFER_TO_FOLLOWUP
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  109:            raw = input(f"     [{q.default}] > ").strip()
fix_suggestion: Use getpass.getpass() to prompt for credentials rather than plain input() # pragma: allowlist secret
withdraw_condition: Add test coverage or explain why this is safe.
citation: SEARCH.json idx:1
```

```reviewer_finding
kind: security
priority: P2
blocking_verdict: DEFER_TO_FOLLOWUP
exploitability: HIGH
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  167:    def __init__(self, path: Path, *, max_cost: float | None = None) -> None:
fix_suggestion: Seed ledger provides fewer guarantees than "append-only ledger" implies: no fsync, no advisory lock. Concurrent adx run invocations interleave appends.
withdraw_condition: Add test coverage or explain why this is safe.
citation: SEARCH.json idx:2
```
