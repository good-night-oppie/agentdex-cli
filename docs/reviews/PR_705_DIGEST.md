---
title: PR 705 Digest
status: active
owner: etang
created: 2026-07-20
updated: 2026-07-20
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

## Summary
This PR fixes `UP038` lint errors (using `X | Y` in an `isinstance` call, which is not supported in `except` blocks in older Pythons, though the specific instances here just collapsed multiple exception types into a tuple) and applies various minor formatting fixes. The PR effectively changes exceptions to use a tuple instead of `|` where appropriate and cleans up whitespace, formatting, and exception strings.

```reviewer_finding
kind: logic
priority: P3
blocking_verdict: APPROVE
exploitability: SAFE
file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
evidence_quote: |
  except (FileNotFoundError, ValueError, OpenboxError) as exc:
fix_suggestion: |
  The PR successfully fixes `UP038` lint errors from a previous PR by changing exception catching to use tuples instead of bitwise ORs (which is the standard way to catch multiple exceptions in Python) and cleans up formatting across several files.
withdraw_condition: "This finding is a review summary and acts as an approval for PR 705."
citation: "SEARCH.json idx:packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py"
```
