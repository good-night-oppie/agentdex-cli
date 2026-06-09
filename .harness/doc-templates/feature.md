<!--
PROPAGATED FROM: /home/admin/gh/harness-engineering/.harness/doc-templates/feature.md
SOURCE SHA at copy time: e019b7d9e7f4ab1c1961cab3137f9d9e42e92ba8e542d630eaa7513e80b69cab
COPIED ON: 2026-06-09
DRIFT DETECTION: re-diff quarterly.
FUTURE: move to ~/.claude/shared-rules/doc-templates/ + pin version per consumer.
-->
---
# REQUIRED FRONTMATTER (validated by doc-lint CI)
title: "<feature name, <=120 chars>"
status: draft            # draft | active | validated | deprecated | archived | experimental
owner: "@github-handle-or-team-slug"
created: 2026-06-09      # YYYY-MM-DD
updated: 2026-06-09
type: feature
scope: "<module-path or service-name>"  # NEVER 'global' for features (DOC-LINT-015)
layer: service           # types | config | data | service | runtime | ui | providers | cross-cutting
rule_class: default      # invariant | default | hint | advisory | informational

# Doc-lint requires these for type=feature
linked_commits: []       # populate with SHAs as commits land (DOC-LINT-052)
linked_issues: []        # MUST be non-empty before status: active (ep08 08-0118)
related:                 # wikilinks must resolve (DOC-LINT-020, ep09 09-0124)
  - "[[docs/architecture/<parent-component>.md]]"

# Every claim must point at a check (ep04 04-0100, ep06 06-0027)
verifiable_claims:
  - claim: "<falsifiable assertion>"
    enforced_by: "tests/test_<feature>.py::test_<assertion>"

# Every normative MUST/SHALL needs a verifier (DOC-LINT-037)
enforced_by:
  - { kind: test,    ref: "tests/test_<feature>.py" }
  - { kind: ci-job,  ref: ".github/workflows/feature-acceptance.yml" }
---

# <Feature Title>

<!--
  Section ordering is enforced by doc-lint.
  Do NOT delete the H2 headers below; the linter checks for their literal presence.
  Per ep03 01-0159 + ep04 04-0332: every section must be falsifiable.
-->

## Problem
<!-- What user/agent need is unmet? Why now? 2-5 sentences. Cite the source signal
     (issue, user transcript, postmortem). No hedging in the "why now" — if you
     can't justify timing, the spec isn't ready. -->

## Solution
<!-- WHAT, not HOW. Describe the user-visible contract / API surface / behavior
     change. Implementation walkthroughs belong below the "Below Invariant Line"
     marker if at all (ep06 06-0050, DOC-LINT-008). -->

## Acceptance Criteria
<!-- DOC-LINT-004: falsifiable checkbox list. No "maybe", "should probably", "TBD".
     Each box is a single assertion a test can decide. Aim for 3-7. -->

- [ ] <observable behavior 1, e.g. "POST /widgets returns 201 with {id, created_at} when payload validates against schema X">
- [ ] <observable behavior 2>
- [ ] <observable behavior 3>

## Translation to Enforcement
<!-- DOC-LINT-041: every Acceptance Criterion above maps to a check.
     No bare TODOs (lint will fail). -->

| AC# | Check kind | Reference                                              |
|-----|------------|--------------------------------------------------------|
| 1   | test       | `tests/test_widgets.py::test_create_widget_happy_path` |
| 2   | schema     | `schemas/widget.create.request.json`                   |
| 3   | ci-job     | `.github/workflows/widget-contract-tests.yml`          |

## Definition of Done
<!-- DOC-LINT-053: single non-empty statement. This is what the agent self-checks
     against before declaring the feature shipped (ep08 08-0313). -->

- All Acceptance Criteria checkboxes pass on CI green
- `linked_commits` populated, all referenced commits merged to main
- Dashboard `dashboards/widgets.json` updated and live (DOC-LINT-058)
- Eval entry `evals/widgets/create.yaml` added or updated (DOC-LINT-059)

## Validation
<!-- How the agent verifies its own work. Executable commands, not prose
     (ep03 02-0206, DOC-LINT-007). Copy-paste runnable. -->

```bash
# Self-review + static checks + tests in one command
make feature.widgets.verify
# expected exit code: 0
```

## Risk
<!-- Forward-looking. What invariant could this break? Which cross-cutting concern
     does it touch (auth, logging, feature-flags) and is the Providers index
     updated (DOC-LINT-047, ep06 06-0242)? -->

- **Invariant at risk:** <e.g. "External-data schema validation at widget ingress"> (rule_class: invariant, ep06 06-0057)
- **Mitigation:** <e.g. "Schema enforced by `schemas/widget.create.request.json`, tested at API boundary">
- **Rollback plan:** <executable command or feature-flag name>

## Citations
<!-- Source-attributed anchors that grounded this design. Use [NN-mmss] format
     matching SEARCH.json (NN = episode number 01-30, mmss = mm:ss timestamp).
     Each cited anchor MUST resolve to an entry in SEARCH.json — doc-lint will
     verify. External links allowed in this section only; primary decisions
     must be mirrored under docs/references/ (DOC-LINT-033). -->

- [03-0341] Skills are first-class artifacts — governs how this feature exposes itself to the harness
- [04-0100] "What do I provide for the agent" framing — drove the Acceptance Criteria shape
- [06-0045] Spec text must be convertible to enforced law — dictated the Translation table above

<!-- ───────────────────────────────────────────────────────────────── -->
<!-- Source: harness-engineering G2 corpus; lint rules: scripts/doc_lint.py -->
<!-- ───────────────────────────────────────────────────────────────── -->

<!-- ============================================================== -->
<!-- EXAMPLE FRAGMENT (delete before merge)                          -->
<!-- ============================================================== -->
<!--
## Acceptance Criteria
- [ ] `harness ingest <playlist.json>` exits 0 when every bvid in the playlist
      has a downloaded mp4 under repo root
- [ ] When a bvid is missing the mp4, exit code is 2 and stderr contains the
      bvid + the missing path
- [ ] Re-running with all files present is a no-op (zero network calls; verified
      by `tests/test_ingest.py::test_idempotent`)

## Translation to Enforcement
| AC# | Check kind | Reference                                  |
|-----|------------|--------------------------------------------|
| 1   | test       | `tests/test_ingest.py::test_happy_path`    |
| 2   | test       | `tests/test_ingest.py::test_missing_bvid`  |
| 3   | test       | `tests/test_ingest.py::test_idempotent`    |
-->
