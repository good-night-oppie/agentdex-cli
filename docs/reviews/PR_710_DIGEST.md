---
title: "PR 710 Digest"
date: "2026-07-30"
status: "active"
owner: "@jules"
created: "2026-07-30"
updated: "2026-07-30"
type: "reference"
scope: "packages/agentdex_cli"
layer: "service"
verifiable_claims: []
---

```reviewer_finding
kind: security
priority: P1
blocking_verdict: BLOCK_MERGE
exploitability: HIGH
file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
evidence_quote: |
  def _scan_strings(backend: str, field_path: str, value: Any) -> None:
fix_suggestion: Empty-path scanner hole is LIVE (AS17-N1). The in-code comment claiming unreachability is false and needs fixing. The `""` path loads cleanly and bypasses the secret check.
withdraw_condition: The empty-path scanner hole is closed and the comment is updated.
citation: SEARCH.json idx:c588f778
exploit_demo: "empty string key"
```

```reviewer_finding
kind: architecture
priority: P1
blocking_verdict: BLOCK_MERGE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  def _cost_dollar_and_kind(
fix_suggestion: Second structural degeneracy (AS17-N3): unmetered models cost exactly $0 and are classified as MEASURED. This lets an unmetered model win the cost axis by construction regardless of output.
withdraw_condition: The `_cost_dollar_and_kind` logic prevents unmetered models from strictly dominating the cost axis.
citation: SEARCH.json idx:c588f778
```

```reviewer_finding
kind: security
priority: P2
blocking_verdict: BLOCK_MERGE
exploitability: HIGH
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  def cmd_interview(args: argparse.Namespace) -> int:
fix_suggestion: `adx interview` scans nothing (AS17-INTERVIEW-UNSCANNED). A credential typed at the pool prompt persists verbatim into the seed ledger and `frontier.json`.
withdraw_condition: Interview inputs are correctly scanned for credentials before saving.
citation: SEARCH.json idx:c588f778
exploit_demo: "pool prompt"
```

```reviewer_finding
kind: architecture
priority: P3
blocking_verdict: DEFER_TO_FOLLOWUP
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
evidence_quote: |
  class FrontierSeedLedger:
fix_suggestion: Seed ledger provides fewer guarantees than "append-only ledger" implies (AS17-LEDGER-DURABILITY). No `fsync`, no advisory lock, no per-row checksum, no schema-version field, mode 0644. Concurrent `adx run` invocations interleave appends (UNSAFE).
withdraw_condition: Ledger durability issues addressed.
citation: SEARCH.json idx:c588f778
```
