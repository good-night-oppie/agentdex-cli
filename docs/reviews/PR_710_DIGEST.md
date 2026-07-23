---
title: PR 710 Digest
status: active
owner: edwardtang
created: 2026-07-23
updated: 2026-07-23
type: reference
scope: agentdex_cli
---

# PR 710 Summary
Changes:
- Implements the contract for openbox<->bridges interaction as outlined in issue #706.
- Updates `DEFERRED.md` reflecting that the OPENBOX-BRIDGES-WIRING issue is closed.
- Documents some findings regarding the AI-Scientist-v2 deep-review.
- Adds uncaught PermissionError fixes in credential paths.

Findings:

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: HIGH
  file: DEFERRED.md
  evidence_quote: "AS17-DENYLIST-GAPS ... Disclosed SECRET_RE misses ... short Basic credentials ... token-as-username URLs with no colon ... scheme-relative ... base64url payloads with -/_ inside the first 16 chars"
  fix_suggestion: "Address the identified regex gaps to catch all basic credentials, token-as-username without colons, scheme-relative URLs, and base64 payloads."
  withdraw_condition: "The gaps in SECRET_RE are patched."
```

```yaml
reviewer_finding:
  kind: logic
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: DEFERRED.md
  evidence_quote: "AS17-N1 ... The empty-path scanner hole was LIVE ... The in-code comment at openbox_cmd.py:159-164 continues to assert 'Not currently reachable'."
  fix_suggestion: "Update the comment in openbox_cmd.py:159-164 to reflect that it is reachable, or patch the call site if the hole is reintroduced."
  withdraw_condition: "The comment in openbox_cmd.py is updated."
```

```yaml
reviewer_finding:
  kind: architecture
  priority: P2
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "Second structural degeneracy: unmetered models cost exactly $0 and are classified as MEASURED."
  fix_suggestion: "Update `_cost_dollar_and_kind` to correctly classify unmetered models and not consider them as measured to fix the dominance issue."
  withdraw_condition: "Unmetered models are not classified as measured."
```
