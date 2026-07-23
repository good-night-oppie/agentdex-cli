---
title: PR 705 Digest
status: active
owner: edwardtang
created: 2026-07-23
updated: 2026-07-23
type: reference
scope: agentdex_cli
---

# PR 705 Summary
Changes:
- Adds a new `.agents/skills/agentdex-interview/SKILL.md` skill description document.
- Modifies `.secrets.baseline` and `.gitignore`.
- Adjusts several files in `.fleet-goal/evidence`.
- Makes updates in `packages/adx_frontier`, `packages/adx_ladders`, and `packages/agentdex_cli` to handle edge cases like missing timestamps (`ts`), negative costs (`cost_dollar`), and NaN quality (`quality`) when analyzing model scores.
- Added extensive tests for `FrontierSeedLedger` and CLI orchestration tools.
- Uses a `_FAKE_SK` in `packages/agentdex_cli/tests/test_run_cmd.py` for negative tests regarding token leaking on CLI error output.

Findings:

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/tests/test_run_cmd.py
  evidence_quote: "_FAKE_SK = \"sk-TESTFAKEabcdefghijklmnop\""  # pragma: allowlist secret
  fix_suggestion: "Remove the hardcoded secret and replace it with a dynamically generated string or mock during tests to avoid triggering secret detection."
  withdraw_condition: "The hardcoded secret is replaced or adequately mocked."
```

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/tests/test_openbox_cmd.py
  evidence_quote: "secret = \"sk-abcdefghijklmnopqrstuvwxyz\""  # pragma: allowlist secret
  fix_suggestion: "Remove the hardcoded secret 'sk-abcdefghijklmnopqrstuvwxyz' in test_openbox_cmd.py."  # pragma: allowlist secret
  withdraw_condition: "The hardcoded credential is removed."
```

```yaml
reviewer_finding:
  kind: logic
  priority: P2
  blocking_verdict: true
  exploitability: SAFE
  file: sweeps/adx-cli-fleet-kanban.json
  evidence_quote: "arena_tui UP038 fixed #283"
  fix_suggestion: "Check whether UP038 fix is actually implemented since PR 705 is titled 'fix(lint): fix UP038 lint errors from PR 704' but there are no UP038 lint violations seen."
  withdraw_condition: "UP038 fixes are present or title is corrected."
```
