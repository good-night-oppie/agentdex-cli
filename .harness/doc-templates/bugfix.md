<!--
PROPAGATED FROM: /home/admin/gh/harness-engineering/.harness/doc-templates/bugfix.md
SOURCE SHA at copy time: 26818a403cf93e9fbf7279907ab2dbcc789ab58f70e86a895cb5257091f957a3
COPIED ON: 2026-06-09
DRIFT DETECTION: re-diff quarterly.
FUTURE: move to ~/.claude/shared-rules/doc-templates/ + pin version per consumer.
-->
---
# REQUIRED FRONTMATTER (validated by doc-lint CI)
title: "<bug short description, <=120 chars>"
status: draft            # draft | active | validated | deprecated | archived
owner: "@github-handle-or-team-slug"
created: 2026-06-09
updated: 2026-06-09
type: bugfix
scope: "<module-path or service-name>"
layer: service           # types | config | data | service | runtime | ui | providers | cross-cutting
rule_class: default

# Doc-lint requires for type=bugfix
linked_commits: []       # repro commit SHA + fix commit SHA
linked_issues: []        # MUST be non-empty (DOC-LINT-049)

# DOC-LINT-049: Repro is required commit-time attachment (ep08 08-0208)
repro:
  steps: "see ## Reproduce below"
  artifact_link: "<URL to video / screenshot / failing-test SHA>"

# DOC-LINT-050: Verified is required pair (ep08 08-0214)
verified:
  steps: "see ## Verify below"
  artifact_link: "<URL to after-state video / passing-test SHA>"

# DOC-LINT-009: agent-bug closures MUST link a gaps.md entry (ep03 02-0298, ep08 08-0136)
gaps_entry: "[[docs/gaps.md#<entry-id>]]"   # set null only if non-agent bug

related:
  - "[[docs/architecture/<owning-component>.md]]"
  - "[[docs/runbooks/<owning-component>.md]]"

verifiable_claims:
  - claim: "The exact failing state in ## Reproduce no longer occurs"
    enforced_by: "tests/test_<component>.py::test_regression_<bug-id>"

enforced_by:
  - { kind: test,   ref: "tests/test_<component>.py::test_regression_<bug-id>" }
  - { kind: ci-job, ref: ".github/workflows/regression-suite.yml" }
---

# Bugfix: <Title>

<!--
  Doc-lint validates that ## Reproduce contains an executable fenced block AND
  ## Verify contains an exit-code-asserting block (DOC-LINT-013, ep04 04-0217).
-->

## Problem
<!-- What was observed vs expected. 2-4 sentences. Cite the user/agent signal
     that triggered the report (issue link, telemetry, agent transcript). -->

- **Observed:** <e.g. "process_batch.py exits 0 but writes empty transcript.txt for videos > 30min">
- **Expected:** <e.g. "non-empty transcript or exit code != 0">
- **First seen:** <date / commit SHA / agent run id>
- **Root cause class:** <agent-env-gap | code-defect | upstream-regression | config-drift>
  <!-- If agent-env-gap: this bugfix MUST touch docs/ or AGENTS.md (DOC-LINT-001). -->

## Reproduce
<!-- DOC-LINT-013: executable fenced block, not prose. Copy-paste runnable.
     End the block with a clear failure signal the agent can detect. -->

```bash
# Setup
cd /home/admin/gh/harness-engineering
FORCE_ASR=1 ./process_batch.py per_video "08_*.mp4"

# Observe failure
test -s per_video/08_*/transcript.txt
# expected: exit 1 (file is zero-length) — this IS the bug
echo "EXIT=$?"
```

Repro artifact: <link to recorded video / screenshot / failing-test commit SHA>

## Solution
<!-- WHAT changed, not a code walkthrough. Reference the fix commit; the diff
     is the source of truth (ep03 01-0128, DOC-LINT-008). -->

- Fix commit: `<SHA>`
- Surface change: <e.g. "exit code 3 emitted when ASR produces empty output, with stderr message naming the input mp4">
- Affected files: <list>

## Verify
<!-- DOC-LINT-013: exit-code-asserting block. -->

```bash
cd /home/admin/gh/harness-engineering
FORCE_ASR=1 ./process_batch.py per_video "08_*.mp4"
test -s per_video/08_*/transcript.txt
# expected: exit 0
echo "EXIT=$? (expect 0)"

# Plus the regression test
pytest tests/test_process_batch.py::test_regression_empty_transcript -q
# expected: exit 0
```

Verified artifact: <link to after-state video / passing-test commit SHA>

## Validation
<!-- Pre-merge self-check the agent runs (ep03 02-0206). -->

```bash
make bugfix.verify BUG_ID=<id>
# expected exit code: 0
```

## Risk
<!-- What might this fix break? Which invariant is touched? -->

- **Invariant touched:** <e.g. "Idempotency of process_batch.py — was it preserved?"> (ep06 06-0101)
- **Regression coverage:** `tests/test_process_batch.py::test_regression_<bug-id>`
- **Rollback:** `git revert <fix-commit-SHA>`

## Gap Closure
<!-- DOC-LINT-009: if root_cause_class == agent-env-gap, this section is mandatory
     and the gaps_entry frontmatter field MUST resolve. -->

- Capability added: <e.g. "process_batch.py now emits exit code 3 + named stderr on empty transcript">
- Doc updated: <link to AGENTS.md or docs/ diff that prevents recurrence>
- Gaps.md entry: [[docs/gaps.md#<entry-id>]]

## Citations
<!-- Source-attributed anchors. Use [NN-mmss] format matching SEARCH.json
     (NN = episode 01-30, mmss = mm:ss timestamp). Each cited anchor MUST
     resolve to a SEARCH.json entry — doc-lint verifies. -->

- [02-0298] Recovery is never "retry" — every failure is a doc gap to fill
- [04-0217] Reproduce + verify + reason are non-negotiable affordances
- [08-0208] Repro artifact required, not nice-to-have
- [08-0214] Verified artifact paired with repro

<!-- ───────────────────────────────────────────────────────────────── -->
<!-- Source: harness-engineering G2 corpus; lint rules: scripts/doc_lint.py -->
<!-- ───────────────────────────────────────────────────────────────── -->

<!-- ============================================================== -->
<!-- EXAMPLE FRAGMENT (delete before merge)                          -->
<!-- ============================================================== -->
<!--
## Reproduce
```bash
./dl_one.py BV1ZY2jBoEZo . 31
# expected exit: 0 (downloads ep31)
# observed:     exit 0 but mp4 is 0 bytes (silent failure)
ls -la 31_*.mp4 | awk '{print $5}'   # prints 0 — THIS IS THE BUG
```

## Verify
```bash
./dl_one.py BV1ZY2jBoEZo . 31
ls -la 31_*.mp4 | awk '{print $5}' | grep -vq '^0$'   # exit 0 expected
```
-->
