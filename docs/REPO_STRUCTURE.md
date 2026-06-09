---
title: agentdex-cli repository structure
status: active
owner: etang
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# REPO_STRUCTURE — agentdex-cli

> Doc-lint baseline (DOC-LINT-005 scaffolding). Reference, not rules —
> all listings are descriptive (no normative `must` / `shall` here; see
> CLAUDE.md / ADR-0009 for the normative layer).

## Top-level layout

```
agentdex-cli/
├── AGENTS.md                          # G2 ep3 navigation index
├── CLAUDE.md                          # contributor doctrine
├── IDEAL_EXPERIENCE.md                # G14 success anchor
├── EVAL.md                            # G13 eval gates
├── AUTONOMY_THRESHOLD.md              # G2 ep6 flip gates
├── DEFERRED.md                        # phase-8 polish queue
├── README.md                          # 1-screen quickstart
├── pyproject.toml                     # uv workspace root + tool config
├── uv.lock                            # locked deps
├── .pre-commit-config.yaml            # ruff + mypy + detect-secrets + sync_toc + doc_lint
├── .secrets.baseline                  # detect-secrets allowlist
├── .gitignore                         # ignores .venv, expeditions/*/trace/, etc.
├── .harness/
│   ├── CORPUS_QUERY_KEYWORDS          # SessionStart hook seed
│   ├── README.md
│   └── doc-templates/                 # doc_lint.py templates
├── .github/
│   └── workflows/                     # lint.yml, debt-sweep.yml
├── agents/                            # G2 ep3 modular per-area docs
│   ├── ops/AGENTS.md
│   ├── build/AGENTS.md
│   ├── debug/AGENTS.md
│   └── review/AGENTS.md
├── cron/                              # autonomous-pipeline wrappers
│   ├── expedition_smoke.sh            # daily smoke gate
│   ├── weekly_harness_audit.sh        # weekly doctrine audit
│   └── dream_consolidate.sh           # KAOS lineage surface
├── docs/
│   ├── architecture/architecture.md   # DOC-LINT-025 baseline
│   ├── adr/                           # ADR-0009 + cascade
│   ├── REPO_STRUCTURE.md              # this file
│   └── DEV_SETUP.md                   # developer onboarding
├── packages/                          # 7-package uv workspace
│   ├── agentdex_cli/                  # CLI entry point
│   ├── agentdex_engine/               # Three Cards + Oracle + Pareto + Expedition
│   ├── agentdex_observe/              # Langfuse wrap + llm_pool
│   ├── agentdex_plugin/               # Hermes plugin glue
│   ├── adx_bridges/                   # claude / codex / manus / codex_web / gemini
│   ├── helios_client/                 # M6+ helios Python client (spec-only)
│   └── kaos/                          # vendored subtree (24.6k LOC)
├── scripts/
│   ├── sync_toc.sh                    # CLAUDE.md TOC generator
│   ├── doc_lint.py                    # 63-rule doc linter (vendored)
│   ├── install_hooks.sh               # pre-commit installer
│   └── install_doc_lint_precommit.sh  # doc-lint pre-commit installer
├── sweeps/                            # weekly audit + dream-consolidate artifacts
├── tasks/                             # frozen TaskCard bundles
│   └── nvidia-earnings-infographic/   # MOCK NVIDIA Q3 FY2026 — replace before live (DEFERRED MOCK-DATA)
├── tests/
│   ├── fixtures/bridges/              # bridge-smoke fixture dir
│   └── golden/                        # nvidia_pareto_expected.yaml
├── tools/
│   └── agent_senses/                  # G2 ep4 read-back loop scripts
│       ├── run_tests.sh
│       ├── peek_metrics.sh
│       ├── tail_logs.sh
│       └── capture_bridge_smoke.sh
└── expeditions/                       # per-Expedition output dirs
    ├── live-001/                      # incomplete (aborted)
    ├── live-002/
    ├── live-003/                      # full 3-bridge live evidence
    └── test-smoke-exp-001/            # gitignored test churn
```

## What lives where (1-liner per top-level)

- **Anchor docs** (`AGENTS.md` / `CLAUDE.md` / `IDEAL_EXPERIENCE.md` /
  `EVAL.md`) — operator surface; lazy-load.
- **`packages/`** — Python source. uv workspace; one strict-mypy island
  in `agentdex_engine/cards/`; everything else opts in per-package.
- **`docs/adr/`** — ADR cascade. ADR-0009 is the unifying meta-ADR.
- **`tasks/`** — frozen TaskCard bundles. BLAKE3 source_bundle_hash is
  the reproducibility anchor.
- **`expeditions/`** — runtime output, one dir per Expedition run.
- **`cron/`** + **`sweeps/`** — autonomous-pipeline mirror from
  `~/gh/eddie-agi-kb/`.
- **`tools/agent_senses/`** — read-back loop scripts; AGENTS.md
  permission manifest references these exact paths.

## Cross-references

- `AGENTS.md` for navigation index
- `docs/architecture/architecture.md` for component contract details
- `docs/DEV_SETUP.md` for developer onboarding
- `IDEAL_EXPERIENCE.md` §1 for operator profile
