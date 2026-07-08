```reviewer_finding
kind: logic
priority: P1
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_arena/src/agentdex_arena/gateway.py
evidence_quote: |
  session.committed = True
fix_suggestion: |
  The PR correctly fixes the post-commit finish failure window (ADX-P0-001 residual) by adding a durable commit point `session.committed = True`. It then handles rating readback failures gracefully by degrading the receipt visibly without throwing a 500 error, and the logic correctly handles `_finish` reentry using the durable commit. The associated unit tests have successfully passed.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 650."
citation: "SEARCH.json idx:packages/agentdex_arena/src/agentdex_arena/gateway.py"
```