# PR 710 Review Digest

**Summary:** This PR formalizes the openbox<->bridges contract, closing the `OPENBOX-BRIDGES-WIRING` issue. It introduces `adx interview` and modifies `openbox` and `run_cmd` to correctly route model names to backend pool configurations.

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: BLOCK_MERGE
  exploitability: HIGH
  file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
  evidence_quote: "_scan_strings"
  fix_suggestion: |
    The `_scan_strings` function has a second call site that passes an empty string as `key_str`, leaving an empty-path scanner hole. Reject empty top-level keys properly or fix the scanner to validate all paths appropriately, and correct the in-code comment asserting "Not currently reachable".
  withdraw_condition: "Once the empty-path scanner hole is fixed and the comment updated."
  citation: "SEARCH.json idx:0"
```

```yaml
reviewer_finding:
  kind: logic
  priority: P1
  blocking_verdict: BLOCK_MERGE
  exploitability: HIGH
  file: packages/agentdex_cli/src/agentdex_cli/openbox_cmd.py
  evidence_quote: "Path.exists()"
  fix_suggestion: |
    Uncaught `PermissionError` paths exist when `Path.exists()` evaluates on unreadable files, returning True, but `read_text` raises. Handle `PermissionError` specifically in `load_openbox` and `_warn_file_ref` instead of letting bare tracebacks escape.
  withdraw_condition: "Once `PermissionError` is caught and handled appropriately."
  citation: "SEARCH.json idx:0"
```

```yaml
reviewer_finding:
  kind: logic
  priority: P2
  blocking_verdict: BLOCK_MERGE
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "_cost_dollar_and_kind"
  fix_suggestion: |
    Unmetered models correctly cost $0, but because they dont end in `-fake`, `_measured_rows` classifies them as measured. As a result, an unmetered model wins the cost axis by construction in dominance checks. Please ensure that unmetered models are treated with the correct fallback cost or excluded from metered optimization comparisons, matching the documented dominance rules.
  withdraw_condition: "Once unmetered models are prevented from bypassing dominance checks on cost."
  citation: "SEARCH.json idx:0"
```

```yaml
reviewer_finding:
  kind: security
  priority: P1
  blocking_verdict: BLOCK_MERGE
  exploitability: HIGH
  file: packages/agentdex_cli/src/agentdex_cli/interview_cmd.py
  evidence_quote: "render_policy_yaml"
  fix_suggestion: |
    The adx interview command uses a bare input() to read configuration answers, and render_policy_yaml serializes these directly into .agentdex/orchestration.yaml (and subsequently into the seed ledger/frontier.json via pool configuration) without running any secret scanning. It is imperative that render_policy_yaml uses SECRET_RE or another guard to detect and reject secrets (like credentials typed accidentally at the pool prompt) before they are written to disk.
  withdraw_condition: "Once user inputs in the interview process are properly scanned for secrets before serialization."
  citation: "SEARCH.json idx:0"
```

```yaml
reviewer_finding:
  kind: logic
  priority: P2
  blocking_verdict: BLOCK_MERGE
  exploitability: SAFE
  file: packages/agentdex_cli/src/agentdex_cli/run_cmd.py
  evidence_quote: "attempts.json"
  fix_suggestion: |
    The seed ledger does not have write-time validation or atomic append guarantees (unlike `attempts.json`), leaving it vulnerable to torn writes and silent row loss when concurrent `adx run` instances interleave appends. Switch the ledger writes to an atomic append method with advisory locking.
  withdraw_condition: "Once seed ledger writes are made safe under concurrency."
  citation: "SEARCH.json idx:0"
```
