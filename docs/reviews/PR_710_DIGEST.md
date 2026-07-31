---
title: "PR 710 Digest"
date: "2026-07-31"
status: "active"
owner: "@jules"
created: "2026-07-31"
updated: "2026-07-31"
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
  SECRET_RE = re.compile(
fix_suggestion: The SECRET_RE regex has multiple gaps: short Basic credentials under the 16-char floor (Basic YWRtaW46cHc=), token-as-username URLs with no colon, scheme-relative //user:pw@host, and base64url payloads with -/_ inside the first 16 chars are not caught.
withdraw_condition: Fix the SECRET_RE denylist to cover short Basic credentials and URL variations.
citation: SEARCH.json idx:9a5e477d
```

```reviewer_finding
kind: security
priority: P1
blocking_verdict: BLOCK_MERGE
exploitability: HIGH
file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
evidence_quote: |
  answers[q.key] = raw or q.default
fix_suggestion: adx interview scans nothing and writes the seed ledger / frontier.json with raw user input. Zero credential persistence does not hold for the interview surface, which may persist credentials verbatim mode 0644.
withdraw_condition: Add SECRET_RE scanning and sanitization to the adx interview command intake flow.
citation: SEARCH.json idx:9a5e477d
```
