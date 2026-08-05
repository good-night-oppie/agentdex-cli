# PR 705 Review Digest

**Summary:** This PR fixes UP038 lint errors from PR 704 and introduces a `SECRET_RE` regex in `openbox_cmd.py` to prevent secrets from being saved.

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: BLOCK_MERGE
  exploitability: HIGH
  file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
  evidence_quote: "SECRET_RE = re.compile(r\"(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{20,}|xoxb-|AKIA[0-9A-Z]{12,})\")"
  fix_suggestion: |
    The `SECRET_RE` regex in `openbox_cmd.py` misses various token formats (like short Basic credentials under the 16-char floor, token-as-username URLs with no colon, scheme-relative `//user:pw@host`, and base64url payloads with `-`/`_` inside the first 16 chars). A more comprehensive regex is needed. However, since the denylist approach has known limitations, a better structural guard might be to rely entirely on `token_ref` rather than extending the regex.
  withdraw_condition: "Once the regex is broadened or the secret detection strategy relies strictly on `token_ref`."
  citation: "SEARCH.json idx:0"
```
