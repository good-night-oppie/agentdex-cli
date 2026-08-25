---
status: active
---

# PR 710 Review Digest

## Summary of Changes
This PR formalizes the `openbox<->bridges` contract. It adds testing around `bridges` proxy fallback quarantine logic (`receipt_kind`, `served_model`), testing for correct handling of looping back base URLs, and ensures robust handling of directory read permissions without exposing raw Python tracebacks (swallowing `PermissionError`).

## Security Evaluation
- Hardcoded Credentials: No hardcoded credentials were added in this PR.
- Secret-Detection Regex Gaps: No changes were made that impact secret detection coverage or regexes.
- Exploitability: SAFE. No security issues found.

## Test Coverage Evaluation
- Coverage is comprehensive. The PR introduces specific tests for `test_serves_model_match_is_a_normal_receipt`, `test_mismatch_is_quarantined`, `test_substituted_row_never_wins_selection`, `test_substituted_row_is_excluded_from_export_but_kept_on_disk`, `test_priced_on_served_model_not_requested`, and handling of `PermissionError` when parsing configs/tokens.

## Verdict
APPROVE. The changes formalize constraints and behavior correctly, introducing appropriate test coverage. No `reviewer_finding` blocks are necessary.
