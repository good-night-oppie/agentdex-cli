---
status: active
title: PR 705 Review Digest
owner: "@good-night-oppie"
created: 2026-07-20
updated: 2026-07-20
type: reference
scope: docs
layer: cross-cutting
cross_cutting: true
verifiable_claims: []
---

# Review PR 705

## Summary
This PR fixes UP038 lint errors from PR 704 and introduces a new interview skill. A security review identified multiple gaps in secret-detection regexes and an unhandled PermissionError escape. Unmetered models are structurally classed as measured, which may affect cost calculations. Missing test coverage was checked: `test_interview_cmd.py` has zero secret-related tests compared to `test_openbox_cmd.py` which has ~15.

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: DEFER_TO_FOLLOWUP
  exploitability: HIGH
  file: DEFERRED.md
  evidence_quote: "AS17-N1 | this row | **The empty-path scanner hole was LIVE, not LATENT"
  fix_suggestion: "Address the empty-path scanner hole identified in AS17-N1 and update related comments."
  withdraw_condition: "If the scanner hole is patched and tests prove it's fixed."
  citation: "SEARCH.json idx:test"
```

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: DEFER_TO_FOLLOWUP
  exploitability: HIGH
  file: DEFERRED.md
  evidence_quote: "AS17-DENYLIST-GAPS"
  fix_suggestion: "Update regexes to catch short Basic credentials and URL userinfo without colons."
  withdraw_condition: "If denylist gaps are deemed acceptable risk."
  citation: "SEARCH.json idx:test"
```

```yaml
reviewer_finding:
  kind: logic
  priority: P2
  blocking_verdict: DEFER_TO_FOLLOWUP
  exploitability: SAFE
  file: N/A
  evidence_quote: "AS17-INTERVIEW-UNSCANNED"
  fix_suggestion: "Add missing test coverage for secret-detection in `adx interview` and remove claims that it scans anything."
  withdraw_condition: "If tests are added or claims removed."
  citation: "SEARCH.json idx:test"
```
