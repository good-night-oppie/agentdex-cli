---
status: active
---

# Review of PR 710: feat(cli,openbox): formalize the openbox<->bridges contract (#706)

## Summary of changes
This PR formalizes the openbox<->bridges contract by validating openbox bindings, enforcing loopback base URLs, substituting candidates when there's a model mismatch, and preventing quarantine leakage into the winner announcements.

## Security & Test Coverage
No hardcoded credentials or secret regex gaps found. Test coverage is explicitly expanded for error/quarantine paths. The `test_token_ref_under_unreadable_parent_warns_and_does_not_raise` accurately checks permission escapes.

## Reviewer Findings
```yaml
- reviewer_finding:
    kind: logic
    priority: P3
    blocking_verdict: APPROVE
    exploitability: SAFE
    file: "N/A"
    evidence_quote: "N/A"
    fix_suggestion: "LGTM. Behavior changes are well covered by new tests."
    withdraw_condition: "N/A"
```
