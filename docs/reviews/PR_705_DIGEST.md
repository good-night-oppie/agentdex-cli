---
title: PR 705 Digest
status: active
owner: jules
created: 2026-08-03
updated: 2026-08-03
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# PR 705 Summary
Changes: Fixes UP038 lint errors (using | instead of tuples with isinstance) across the codebase.

## Findings

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/tests/test_openbox_cmd.py
  evidence_quote: 'secret = "sk-abcdefghijklmnopqrstuvwxyz # pragma: allowlist secret"'
  fix_suggestion: 'Append ` # pragma: allowlist secret` to the hardcoded secret to prevent detect-secrets from flagging it in tests.'
  withdraw_condition: 'The `pragma: allowlist secret` is appended or the credential is removed.'
```

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/tests/test_openbox_cmd.py
  evidence_quote: 'secret_key = "sk-TESTFAKEkeyvaluexx # pragma: allowlist secret"'
  fix_suggestion: 'Append ` # pragma: allowlist secret` to the hardcoded secret to prevent detect-secrets from flagging it in tests.'
  withdraw_condition: 'The `pragma: allowlist secret` is appended or the credential is removed.'
```

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: true
  exploitability: SAFE
  file: packages/agentdex_cli/tests/test_run_cmd.py
  evidence_quote: '_FAKE_SK = "sk-TESTFAKEabcdefghijklmnop # pragma: allowlist secret"'
  fix_suggestion: 'Append ` # pragma: allowlist secret` to the hardcoded secret to prevent detect-secrets from flagging it in tests.'
  withdraw_condition: 'The `pragma: allowlist secret` is appended or the credential is removed.'
```
