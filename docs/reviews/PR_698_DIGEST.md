---
title: PR 698 Digest
status: active
owner: etang
created: 2026-07-15
updated: 2026-07-15
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---
```reviewer_finding
kind: logic
priority: P1
blocking_verdict: APPROVE
exploitability: SAFE
file: scripts/clean_state.py
evidence_quote: |
  # A malformed config is a REPO problem, not a gate crash: pre-commit
  # itself cannot load the file, so no hook in it runs. Report it as a
  # FINDING (exit 1) — never an internal error (exit 2), never a
  # traceback.
fix_suggestion: |
  The PR correctly fixes the exit-code contract divergence in `scripts/clean_state.py` when `pyyaml` is not installed on `ubuntu-latest`. It properly handles the `yaml.YAMLError` and returns a `Finding` (exit 1) rather than crashing (exit 2), ensuring that CI environments without `pyyaml` behave consistently with developer environments. Installing `pyyaml` in `.github/workflows/clean-state-gate.yml` further pins the environment to match local execution.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 698."
citation: "SEARCH.json idx:exit-code-divergence"
```
