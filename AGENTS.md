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
- [ADR-0010 (arena)](docs/adr/0010-arena-repromotion.md) — Showdown arena lane as expedition variant; Glicko-delta receipt; lanes + consent + cuts
- [ADR-0011 (GTM-A)](docs/adr/0011-gtm-a-membership-primitive-and-paid-feature-positioning.md) — per-owner monthly membership primitive + repositioned paid feature surface (badge SVG + signed replay + bulk API + regression gate); anti-pay-to-rank invariant
- [ADR-0012 (scale)](docs/adr/0012-arena-partitioning-and-scale-to-100-concurrent.md) — battle_id is the partition key (share-nothing, single-writer/battle); scale to ~100 concurrent via SidecarPool + battle routing; recover via inputLog/serializeBattle; ladder = incremental cached derived view; multiplayer routes by battle_id not user_id
- [Membership admin runbook](docs/runbooks/membership-admin.md) — operator-only: generate admin token, set Koyeb env, grant/revoke/rotate (NOT for agent clients)
- [arena deploy go/no-go](docs/references/2026-06-11-arena-deploy-gonogo.md) — measured Spaces/Koyeb contract, sidecar RSS, determinism finding, durable-store choice
- [arena calibration report](docs/references/2026-06-12-arena-calibration.md) — anchor ordering + 2·RD separation PASS in 200 battles; selftest wiring
- [arena fun + multi-dim + reward-hack design](docs/references/2026-06-12-arena-fun-multidim-rewardhack-design.md) — Will Wright × Lilian Weng synthesis: 4 fun moves = 4 capability dimensions, each shipped with the anti-reward-hack defense it needs (phases 9–11 backlog)
- [arena playtest dogfood](docs/references/2026-06-12-arena-playtest-dogfood.md) — 3 real agent CLIs (codex/agy/claude) played the loop; independently validated #2/#3/#6/SDK; fixed capacity-503 + owner-validation; top remaining = battle observability
- [BENE-Supabase event sourcing](docs/references/2026-06-12-bene-supabase-event-sourcing.md) — two-tier design (server Supabase Postgres authoritative mirror / client SQLite); RLS per consent token proven on PG16; O(1) chain append; write-behind mirror; WASM-in-browser rejected (appendix)
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
- [EvoMap deep-dive](docs/references/2026-06-11-evomap-deep-dive.md) — adversarially-verified dossier; Gene-vs-Seed anatomy + Delta-Meter case study (#562)

## Learned notes

- [learned-notes.md](agents/learned-notes.md) — user preferences + workspace facts (promoted out of index per DOC-LINT-021)
