---
title: AGENTS.md — agentdex-cli
status: active
owner: etang
created: 2026-06-07
updated: 2026-06-09
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# AGENTS.md

- Map (not encyclopedia) per [G2 ep3 pattern](docs/architecture/architecture.md)
- Lazy-load linked surfaces — do not paste this file into the agent
- Foundation: [CLAUDE.md](CLAUDE.md) + [IDEAL_EXPERIENCE.md](IDEAL_EXPERIENCE.md) + [EVAL.md](EVAL.md)

## Tools

- [uv workspace](pyproject.toml) — workspace pkg manager
- [pytest runner](tools/agent_senses/run_tests.sh) — canonical test command
- [pre-commit config](.pre-commit-config.yaml) — ruff + mypy + secrets + sync_toc + doc_lint
- [doc_lint.py](scripts/doc_lint.py) — 63 rules vendored from harness-engineering
- [sync_toc.sh](scripts/sync_toc.sh) — CLAUDE.md TOC generator
- [install_hooks.sh](scripts/install_hooks.sh) — pre-commit installer
- [install_doc_lint_precommit.sh](scripts/install_doc_lint_precommit.sh) — doc-lint installer
- [expedition_smoke.sh](cron/expedition_smoke.sh) — daily smoke gate
- [weekly_harness_audit.sh](cron/weekly_harness_audit.sh) — doctrine drift scan
- [dream_consolidate.sh](cron/dream_consolidate.sh) — KAOS lineage surface
- [capture_bridge_smoke.sh](tools/agent_senses/capture_bridge_smoke.sh) — bridge fixture capture
- [tail_logs.sh](tools/agent_senses/tail_logs.sh) — peek heartbeat logs
- [peek_metrics.sh](tools/agent_senses/peek_metrics.sh) — system shape signal

## Architecture

- [ADR-0009 (canonical)](docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md) — KAOS substrate + retrofit + Pokédex pivot
- [docs/architecture/architecture.md](docs/architecture/architecture.md) — TOOLS / ARCH / CONTEXT + invariants + guardrails
- [docs/REPO_STRUCTURE.md](docs/REPO_STRUCTURE.md) — top-level tree
- [docs/DEV_SETUP.md](docs/DEV_SETUP.md) — env vars + first-run + common workflows
- [supergoal ROADMAP](.supergoal/ROADMAP.md) — phase progress + Notable events log
- [DEFERRED.md](DEFERRED.md) — phase-8 polish queue w/ `Until:` dates
- [agents/ops/AGENTS.md](agents/ops/AGENTS.md) — env vars + secrets + ports
- [agents/build/AGENTS.md](agents/build/AGENTS.md) — build / test / lint commands
- [agents/debug/AGENTS.md](agents/debug/AGENTS.md) — failure modes + log locations
- [agents/review/AGENTS.md](agents/review/AGENTS.md) — merge philosophy + escalation

## Context

- [IDEAL_EXPERIENCE.md](IDEAL_EXPERIENCE.md) — operator profile + 6 ideal moments + 5 drift cases (G14)
- [EVAL.md](EVAL.md) — eval gates + ground-truth dataset (G13)
- [CLAUDE.md](CLAUDE.md) — doctrine commitments
- [AUTONOMY_THRESHOLD.md](AUTONOMY_THRESHOLD.md) — supervised → autonomous flip gates (G2 ep6)
- [memory dir](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/) — feedback / project / reference notes
- [adr cascade](docs/adr/) — historical decisions
- [.harness/CORPUS_QUERY_KEYWORDS](.harness/CORPUS_QUERY_KEYWORDS) — SessionStart hook seed
- [.harness/doc-templates/](.harness/doc-templates/) — doc-lint template starters

## Feedback

- [run_tests.sh](tools/agent_senses/run_tests.sh) — is the codebase green?
- [peek_metrics.sh](tools/agent_senses/peek_metrics.sh) — system shape signal
- [tail_logs.sh](tools/agent_senses/tail_logs.sh) — last expedition trace
- [weekly_harness_audit.sh](cron/weekly_harness_audit.sh) — doctrine drift scan
- [dream_consolidate.sh](cron/dream_consolidate.sh) — KAOS lineage surface
- [doc_lint.py](scripts/doc_lint.py) — commit-gate doc rules
- [monitor-gaps.md](~/.cursor/projects/home-admin/heartbeat/monitor-gaps.md) — error funnel (1h sweep cadence)
- [sweeps/](sweeps/) — audit artifacts
- [feedback_gap_log_review memory](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_gap_log_review.md) — review cadence
- [AAOP MVP verdicts](docs/references/2026-06-10-aaop-mvp-verdicts.md) — 16-paper corpus → 6 refuted MVPs + whitespace (phase-9 strategy anchor)

## Learned notes

- [learned-notes.md](agents/learned-notes.md) — user preferences + workspace facts (promoted out of index per DOC-LINT-021)
