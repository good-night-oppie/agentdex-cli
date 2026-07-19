---
title: AGENTS.md — agentdex-cli
status: active
owner: etang
created: 2026-06-07
updated: 2026-06-25
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
enforced_by:
  - .github/workflows/pr-cascade-breaker-gate.yml
  - scripts/pr_cascade_breaker_gate.py
  - scripts/enforce_review_bounds.sh
---

# AGENTS.md

- Map (not encyclopedia) per [G2 ep3 pattern](docs/architecture/architecture.md)
- Lazy-load linked surfaces — do not paste this file into the agent
- Foundation: [CLAUDE.md](CLAUDE.md) + [IDEAL_EXPERIENCE.md](IDEAL_EXPERIENCE.md) + [EVAL.md](EVAL.md)

## CI-POLICY

Standing, fleet-wide (per Eddie; A2A `shared_log#357`). Do NOT chase full-green CI.

- WHY: repo has no required-status-check branch protection, and full-tree `pre-commit run --all-files` can transiently red on third-party / sibling-synced content the repo doesn't own — chasing 0-red on that noise is waste (PRs #251/#253/#199 — do not repeat). (`vendor/aaop/**` is globally hook-excluded in [.pre-commit-config.yaml](.pre-commit-config.yaml) so it never reds; the bene blog HTML that *did* red full-tree was durably hook-excluded in #253.)
- DO: merge on the REAL gates only (your change's own lint+test checks + your tests); accept a full-tree pre-commit red caused by third-party / synced files you did not touch. `gh pr merge --squash` (no `--admin`).
- STILL: fix a regression YOUR diff causes (green→red); keep fix-all tiny-PR cadence; add no make-CI-green PRs.
- See [agents/review/AGENTS.md](agents/review/AGENTS.md) — merge philosophy (its full-green auto-merge criteria are scoped by THIS policy: the gate is your change's own checks, not full-tree green; they are also gated OFF until `AUTONOMY_THRESHOLD.md` flips AUTONOMOUS).

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
- [ADR-0013 (onboarding)](docs/adr/0013-first-time-user-onboarding-pip-login-wizard.md) — proposed/design-first first-time-user journey: `pip install agentdex-cli[bene]` → `adx login` (GitHub device-flow) → `adx onboard` wizard → account-authed enroll → play (MCP/`adx arena play`) → `adx status`; account↔consent-token bridge reuses today's `ConsentAuthority`; adx-cli↔adx-core wire-contract split; release to PyPI last (once play-ready)
- [ADR-0014 (poke-env)](docs/adr/0014-pokeenv-battle-substrate-and-codex-bene-evolution.md) — proposed/design-first: poke-env + a real Pokémon Showdown server replace the `adx_showdown` sidecar; gateway platform features (consent/quota/membership/badge/ladder/replay/EventLog) + Three-Cards/Pareto unchanged; two-loop evolution — Codex auto-drive proposes, BENE win-rate probe + kill gate promotes; local-first then `54.203.252.69`
- [ADR-0015 (evolution ladder)](docs/adr/0015-evolution-ladder-redesign.md) — draft: Agent Evolution Ladder redesign — supersedes the invited-user GA story; AgentCandidate manifest; 3-layer RSI loop (weco start claude drives, weco run inner mutation, bene mh frontier + kill-gated promotion); axes-at-budget frontier partitioned by (ladder, base_model); two-class ladder taxonomy (live-adversarial vs static + HF substrate); v1 adapters ARC-AGI-3 + TB2 + PokeAgent; two-tier trust ledger; knowledge→market→leaderboard site spine
- [Membership admin runbook](docs/runbooks/membership-admin.md) — operator-only: generate admin token, set Koyeb env, grant/revoke/rotate (NOT for agent clients)
- [Arena go-live runbook](docs/runbooks/arena-go-live.md) — operator-only: pre-flight env contract (fail-closed vs soft-degraded), dev→main promotion deploy, SidecarPool scaling, /healthz+/metrics thresholds, SHA-attested rollback
- [arena deploy go/no-go](docs/references/2026-06-11-arena-deploy-gonogo.md) — measured Spaces/Koyeb contract, sidecar RSS, determinism finding, durable-store choice
- [arena calibration report](docs/references/2026-06-12-arena-calibration.md) — anchor ordering + 2·RD separation PASS in 200 battles; selftest wiring
- [arena fun + multi-dim + reward-hack design](docs/references/2026-06-12-arena-fun-multidim-rewardhack-design.md) — Will Wright × Lilian Weng synthesis: 4 fun moves = 4 capability dimensions, each shipped with the anti-reward-hack defense it needs (phases 9–11 backlog)
- [arena playtest dogfood](docs/references/2026-06-12-arena-playtest-dogfood.md) — 3 real agent CLIs (codex/agy/claude) played the loop; independently validated #2/#3/#6/SDK; fixed capacity-503 + owner-validation; top remaining = battle observability
- [arena load-test measured](docs/references/2026-06-17-arena-loadtest-measured.md) — `scripts/arena_loadtest.py` per-sidecar curve (ADR-0012 #1): memory FLAT ~197MB (96MB heap cap, not linear); limiter = single-thread event-loop latency (p95 13→422ms over N=1→32, zero think-time worst case); sim cheaper than feared → ~2–4 sidecars for 100, LLM tier is the real bottleneck
- [EventLog append throughput](docs/references/2026-06-23-eventlog-append-throughput.md) — `scripts/eventlog_append_bench.py` for ADR-0012 #2; current NDJSON `append` clears 100 turns/sec at N=100, while aged-log `append_many` is not safe as a hot-path grouped writer
- [LLM proxy fan-out measured](docs/references/2026-06-23-llm-proxy-measured.md) — `scripts/llm_proxy_measure.py` for ADR-0012 #3; current run reached `/v1/models` but blocked on upstream provider balance/auth before 100-concurrent data
- [Showdown × Human-vs-AI UI/UX digest](docs/references/2026-06-17-showdown-ux-hvai-digest.md) — battle-render / reasoning-surface / spectator / replay / ladder / TUI design distilled from @pkmn + CloudRetro + Showdown clients + PokemonLLMBattleAI + Gemini-Plays-Pokémon; one typed `|pipe|` protocol → reducer, `(seed,inputLog)` verifiable replay, `{reason,action}` schema, P1/P2/P3 UX backlog
- [arena typed line-protocol](docs/references/2026-06-17-arena-line-protocol.md) — the `|TYPE|args` message-set spec (P1-a): major/minor/meta tier rule, `lineproto.MESSAGE_TYPES` registry (90 types), `|split|` secret-sharing → fog-of-war, `|t:|` strip-for-hash, kwarg `[from]`/`[of]` semantics; the single wire format adx-sim/client/view all fold over
- [BENE-Supabase event sourcing](docs/references/2026-06-12-bene-supabase-event-sourcing.md) — two-tier design (server Supabase Postgres authoritative mirror / client SQLite); RLS per consent token proven on PG16; O(1) chain append; write-behind mirror; WASM-in-browser rejected (appendix)
- [docs/architecture/architecture.md](docs/architecture/architecture.md) — TOOLS / ARCH / CONTEXT + invariants + guardrails
- [release pipeline design](docs/superpowers/specs/2026-06-21-release-pipeline-design.md) — release pipeline design
- [release pipeline plan](docs/superpowers/plans/2026-06-21-release-pipeline.md) — release pipeline plan
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
- [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md) — where issues live (GitHub); what is NOT skill-writable
- [docs/agents/triage-labels.md](docs/agents/triage-labels.md) — the 5 canonical triage label strings
- [docs/agents/domain.md](docs/agents/domain.md) — domain-doc consumer rules (single-context)
- [harness HA orchestrator design](docs/references/2026-07-11-harness-ha-orchestrator-design.md) — HA orchestrator design (draft)
- [clean-state runbook](docs/runbooks/clean-state.md) — tracked-or-ignored rule; pre-commit / lint / CI / worktree gates

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

## PR Cascade Breaker — reviewer protocol

All PR reviewers operating on this repo MUST walk the `pr-cascade-breaker` finite state machine. The 11 hard rules live in [agents/review/AGENTS.md §"PR Cascade Breaker"](agents/review/AGENTS.md). Canonical skill: `~/.claude/skills/pr-cascade-breaker/SKILL.md` (synthesised 2026-06-25 from 6 historical cascade post-mortems). CI: `.github/workflows/pr-cascade-breaker-gate.yml`.

## Reviews
- [PR 621 Digest](docs/reviews/PR_621_DIGEST.md)
- [PR 623 Digest](docs/reviews/PR_623_DIGEST.md)
- [PR 624 Digest](docs/reviews/PR_624_DIGEST.md)
- [PR 649 Digest](docs/reviews/PR_649_DIGEST.md)
- [PR 689 Digest](docs/reviews/PR_689_DIGEST.md)
- [PR 694 Digest](docs/reviews/PR_694_DIGEST.md)
- [PR 695 Digest](docs/reviews/PR_695_DIGEST.md)
- [PR 696 Digest](docs/reviews/PR_696_DIGEST.md)
- [PR 650 Digest](docs/reviews/PR_650_DIGEST.md)
- [PR 651 Digest](docs/reviews/PR_651_DIGEST.md)
- [PR 652 Digest](docs/reviews/PR_652_DIGEST.md)
- [PR 698 Digest](docs/reviews/PR_698_DIGEST.md)
- [PR 701 Digest](docs/reviews/PR_701_DIGEST.md)
- [PR 702 Digest](docs/reviews/PR_702_DIGEST.md)
- [PR 705 Digest](docs/reviews/PR_705_DIGEST.md)
- [PR 710 Digest](docs/reviews/PR_710_DIGEST.md)
- [PR 705 Digest](docs/reviews/PR_705_DIGEST.md)
- [PR 710 Digest](docs/reviews/PR_710_DIGEST.md)

## Droid skills (global)

Droid sessions in this repo can load the following skills from `~/.factory/skills/`.
Activate by skill name when the task matches the trigger.

| Skill | Use when | Trigger keywords |
|---|---|---|
| `ai-scientist` | AI-Scientist-v2 research workflows, BFTS experiments, paper/review stages, run ledgers | ai-scientist, BFTS, experiment, novelty, paper, writeup |
| `bene` | Multi-agent harness, engrams, probes, kill gates, BENE CLI/MCP, fleet meta-harness | bene, engram, probe, kill gate, mh search, autonomy ladder |
| `fleet-doctor` | Fleet stall/restart/OOM recovery, session/daemon revival, health checks | fleet-doctor, revive fleet, fleet health, bootstrap fleet, self-heal |
| `fleet-enroll` | Fleet enrollment, A2A bus registration, sweep watch, fleet comms, COLLAB_CAPSULE | fleet-enroll, enroll, A2A, collab capsule, watch coverage |
| `mroute` | Service-facing task routing, dispatch worker selection, cross-lineage handoff | mroute, route task, dispatch worker, fleet router, cross-lineage |
| `orch-proj` | Long-running project orchestration, milestones, evidence gates, subagent delegation | orch-proj, milestone, fleet-goal, collab capsule, delegate, long-term project |
| `prisma_deep_plan` | Deep planning, architecture decisions, debugging, reviews via the Prisma planner | prisma deep plan, deep planning, architecture review, refactoring plan |
| `weco` | Code optimization against measurable metrics (speed, accuracy, cost, memory) | weco, optimize, make it faster, reduce latency, lower cost |

Skill files live under `~/.factory/skills/<skill>/SKILL.md`. For runtimes without a
native skill loader, read the relevant SKILL.md into context.
