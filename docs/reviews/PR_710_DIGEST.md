---
status: active
---
# PR 710 Review Digest

## Changes Summary
This PR implements the openbox<->bridges contract (closing issue #706). It updates the `adx run --engine bridges` behavior to properly wire per-slot `base_url` bindings instead of silently ignoring `.agentdex/openbox.yaml`. It also catches `PermissionError` independently in the credential path and addresses documentation gaps related to secret scanning.

## Security Evaluation
```yaml
reviewer_finding:
  kind: "security"
  priority: "blocking"
  blocking_verdict: "Documentation notes known SECRET_RE misses for short Basic credentials, token-as-username URLs, and scheme-relative URLs."
  exploitability: "low"
  file: "DEFERRED.md"
  evidence_quote: "Disclosed SECRET_RE misses, recorded so they are greppable rather than rediscovered: short Basic credentials under the 16-char floor (Basic YWRtaW46cHc= = admin:pw) are not caught; token-as-username URLs with no colon (https://<token>@host/v1) load at rc 0;"
  fix_suggestion: "Address the regex gaps in `SECRET_RE` to cover these cases."
  withdraw_condition: "Regex gaps are addressed or explicitly scoped out in the code review."
```

## Missing Test Coverage
No missing test coverage flagged. Tests for `openbox_bridges_contract`, `test_openbox_cmd`, and `test_run_cmd` were added/updated.
