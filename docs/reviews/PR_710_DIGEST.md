---
status: active
title: "Review Digest for PR #710"
---

# Review Digest for PR #710

**Summary:** This PR formally implements the `openbox<->bridges` contract by reading `.agentdex/openbox.yaml` for routing per-backend bindings, ensuring model routing and API bindings are properly applied. It also addresses the empty-path scanner hole, adds `PermissionError` handling in credential loading paths, tracks metrics/measurements for models to ensure unmetered models don't automatically win, and updates `DEFERRED.md`.

**Missing test coverage / Test issues:**
- The PR seems to include regression tests in `test_openbox_cmd.py` and `test_openbox_bridges_contract.py` which is good. Needs verification that all new behavior correctly updates the test suite.

**Security issues:**
- The PR implements a fix for empty-path scanner hole (AS17-N1) and unhandled `PermissionError` (AS17-N2).
- The PR records AS17-DENYLIST-GAPS (short basic credentials, token-as-username URLs) and AS17-INTERVIEW-UNSCANNED (adx interview scans nothing).
- However, since this is a feature branch and I only see the diffs for these fixes, there are no *new* security regressions introduced here based on a scan of the diffs.

```yaml
reviewer_finding:
  kind: security
  priority: P2
  blocking_verdict: true
  exploitability: HIGH
  file: DEFERRED.md
  evidence_quote: "AS17-INTERVIEW-UNSCANNED"
  fix_suggestion: "While this PR mentions that `adx interview` scans nothing and credentials persist verbatim into the seed ledger, it only updates the doc. It is recommended to add `SECRET_RE` scanning to `interview_cmd.py` to prevent credential leakage. (Unless this is scoped to a future PR per DEFERRED.md)."
  withdraw_condition: "Author clarifies that the fix for AS17-INTERVIEW-UNSCANNED is out of scope for this PR and tracked separately."
```
