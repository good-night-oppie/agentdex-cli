---
title: PR 705 Digest
status: active
owner: jules
created: 2026-08-16
updated: 2026-08-16
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# PR 705: fix(lint): fix UP038 lint errors from PR 704

## Summary
This PR fixes `UP038` lint errors introduced in a previous PR (#704). It refactors several exception raises in `candidate.py` and `base.py` to be single-line statements and cleans up `.secrets.baseline`.

## Checks
- **Correctness:** The refactoring maintains identical behavior while satisfying the linter.
- **Security:** No hardcoded credentials or new secrets were found. The changes to `.secrets.baseline` correctly remove previously excluded secret paths which are no longer needed.
- **Test Coverage:** This is a lint-fix chore PR. No new features are added, so test coverage requirements are satisfied by existing CI tests passing.


```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/adx_frontier/src/adx_frontier/candidate.py
evidence_quote: raise CandidateValidationError(f"invalid mutable glob {pattern!r}: {exc}") from exc
fix_suggestion: The PR correctly resolves lint errors by putting exceptions on one line. No logic bugs were found. This serves as an approval since this is a chore/sync PR.
withdraw_condition: Approving as sync/chore PR.
citation: SEARCH.json idx:packages/adx_frontier/src/adx_frontier/candidate.py
```
