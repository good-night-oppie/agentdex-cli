# PR 710 Review Digest

**Summary:** This PR formalizes the openbox<->bridges contract by validating `serves_model` and introducing a substitution quarantine for mismatched models.

```yaml
- reviewer_finding:
    kind: logic
    priority: P3
    blocking_verdict: APPROVE
    exploitability: SAFE
    file: "packages/agentdex_cli/src/agentdex_cli/run_cmd.py"
    evidence_quote: |
      def test_substituted_candidate_is_never_announced_as_winner
    fix_suggestion: |
      The implementation handles substitution correctly. Approved.
    withdraw_condition: |
      None.
```
