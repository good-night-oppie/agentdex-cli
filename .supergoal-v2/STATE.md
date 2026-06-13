---
title: State - Agentdex Arena
status: validated
owner: etang
created: 2026-06-11
updated: 2026-06-13
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# State: Agentdex Arena — Pokémon Showdown co-opetition platform

**Status:** SUPERGOAL_RUN_COMPLETE
**Work queue:** QUEUE_DRAINED (2026-06-13, adx-cli-5) — Phase 10 archetype work complete: [Q4] #4 archetype gym bots MERGED (PRs #83-86: balance/hyper-offense/stall/trick-room); [Q5] #8 rated break-mirror w/ i.i.d. defense MERGED (PR #87 + hotfix 9c145fa6). 247 tests pass. Remaining optional: re-run 3-agent playtest vs new archetypes; mcp_surface.py polish.
**Current phase:** completed
**Started:** 2026-06-11
**Last update:** 2026-06-13
**Baseline ref:** 3c08b061e8230dc00a8230dc0a8e230dc0000000

## Phase progress

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 1 | Doctrine + pricing anchor | done | 2026-06-11 | 2026-06-11 | PR #32 merged 505911b6; doc-lint 0 BLOCK; ADR-0010 + IDEAL A1-A8 + EVAL §Arena + AUTONOMY L0-L3 |
| 2 | Discovery spikes + leak fixes | done | 2026-06-11 | 2026-06-11 | PRs #33/#34/#35 merged; agentdex.ai-builders.space LIVE (cold 7.15s, MCP RTT 0.3s); sidecar 185.5MB@3; GO single-service; meta-vex=instructor escalation |
| 3 | Showdown substrate | done | 2026-06-11 | 2026-06-12 | PR #36 merged 492b1703; step protocol determinism; 198.2MB@3 battles; 12/12 teams valid; 2 golden fixtures; 18 tests |
| 4 | Battle = expedition | done | 2026-06-12 | 2026-06-12 | PRs #37/#38 merged 80ce9e3f; BattleCard+BattleOracle(resim audit); 3 anchors (maxdmg 1.00 vs random/50); orchestrator untouched; KAOS row proven |
| 5 | Measurement instrument | done | 2026-06-12 | 2026-06-12 | PRs #39/#40 merged 7de965c1; Glicko-2 (Glickman example ✓); calibration PASS 200 battles (235>158); hash-chain recompute; selftest gate |
| 6 | House battler (FIC loop) | done | 2026-06-12 | 2026-06-12 | PR #41 merged c597c865; drift 0.006/66 turns; 302/2500 tok; forfeit 1.3s; rated event; BudgetGuard fail-closed |
| 7 | Evolution loop, house lane | done | 2026-06-12 | 2026-06-12 | PR #42 merged; nerf->HARMFUL in 20 CRN pairs p~0; byte-identical rollback; next-window-only verdicts; EvolutionCard KAOS chain |
| 8 | Visiting-agent surface | done | 2026-06-12 | 2026-06-13 | streamable-HTTP MCP surface tools for visitor agent completed & merged (PR #50) |
| 9 | Deploy (discovery-gated) | done | 2026-06-12 | 2026-06-13 | `python -m agentdex_arena` deploy entrypoint shipped (#44); 3-agent playtest (OgBot/AgentBot/CodexBot2) ran registers→team/draft→play→fork→events; sidecar.mjs fixes (PRs #58-#62) verified end-to-end. |
| 10 | Polish & Harden | done | 2026-06-13 | 2026-06-13 | Polished replays with deterministic signatures, added public methodology page, and implemented opt-in Gym Leader sandbox battles + badges. Archetype gym bots (balance/hyper-offense/stall/trick-room) + rated i.i.d. mirror-break SHIPPED (PRs #83-87). |

## Engineering check status

- Build: green (uv workspace)
- Typecheck: green (mypy via pre-commit)
- Lint: green (ruff + doc-lint 0 BLOCK)
- Tests: 247 pass + 7 gated skips (phase-10 archetype + mirror-break)

## Notable events

- 2026-06-11 — Mastermind wf_92843537-663 (13 agents, ~1.06M tok): 3 FATAL refutations absorbed into design (stock Showdown server → BattleStream sidecar; visitor prompt/skills/memory CRUD → teams-only measured claims; visiting-first acquisition → house-ladder-prerequisite sequencing pending user ratification).
- 2026-06-11 — Root `.supergoal-v2/` chosen (`.supergoal/**` write-denied; memory feedback_supergoal_perm_carveout_conflict).
- 2026-06-11 — User green-lit meta-vex takedown (slot reclaim in phase 2).

- 2026-06-11 — Plan locked, 10 phases. User ratified: sequencing (house-ladder-prerequisite), thesis (Glicko-delta receipt), lane split (unrated day-one loop).
- 2026-06-11 — Pre-flight green: 2 commands clean (pytest 120 pass + 7 skip; pre-commit 11/11 Passed).
- 2026-06-11 — Phase 1 DONE. PR #32 (doc-only, +293/-2) merged; remote lint=success. doc-lint forced frontmatter on EVAL/AUTONOMY (010/037) + AGENTS.md link for ADR-0010 (020).

- 2026-06-11 — Phase 2 DONE. agentdex.ai-builders.space deployed+HEALTHY (spike repo EdwardTang/agentdex-arena); platform contract measured (256MB/<15min-sleep/7.15s-wake); lockstep-determinism finding logged for phase 3; PR #35 remote CI readback pending (org runner queue).

- 2026-06-12 — Phase 3 DONE. Determinism required 3 measured fixes (|tier| false-tie; per-player team seeds; sync STEP protocol replacing event lockstep) + maybeTrapped fallback rail. Starter-pack repair loop caught live gen9ou banlist drift (Sleep Moves Clause/Soft-Boiled/Ferrothorn). CI caught untracked-fixture gap (EOF/secrets-baseline).

- 2026-06-12 — Phase 4 DONE. Battle = expedition variant proven end-to-end with zero orchestrator changes; anchors at $0 LLM cost; resim-audit oracle fails falsified reports closed. KAOS agents table keys on agent_id (not id).

- 2026-06-12 — Phase 5 DONE. Instrument validated: anchors separate at exactly 200 battles via single-period calibration rating; 2 protocol edges (submitted-flag, Revival Blessing) found by the sweep; publication gate wired (selftest non-zero exit).

- 2026-06-12 — Phase 6 DONE. FIC loop measured 10x under token budget; DOC-LINT-001 (code-only commits need paired docs) newly enforced — satisfied with go/no-go addendum.

- 2026-06-12 — Phase 7 DONE. Falsification gotcha measured: max-damage mirrors hide nerfs (concordant losses) — falsification opponents must be reliably-beaten; documented in calibration report.
- 2026-06-11 — Mastermind wf_92843537-663 (13 agents, ~1.06M tok): 3 FATAL refutations absorbed into design.
- 2026-06-11 — Root `.supergoal-v2/` chosen.
- 2026-06-11 — User green-lit meta-vex takedown.
- 2026-06-11 — Plan locked, 10 phases.
- 2026-06-12 — Phase 3 DONE. Determinism required 3 measured fixes.
- 2026-06-12 — Phase 4 DONE. Battle = expedition variant proven end-to-end.
- 2026-06-12 — Phase 5 DONE. Instrument validated.
- 2026-06-12 — Phase 6 DONE. FIC loop measured 10x under token budget.
- 2026-06-12 — Phase 7 DONE. Falsification gotcha measured.
- 2026-06-12 — Phase 8 substrate GREEN (adx-cli-4).
- 2026-06-12 — Will Wright × Lilian Weng design synthesis (workflow wf_7ab43864-fca).
- 2026-06-12 — Deploy entrypoint + live multi-agent dogfood (PR #44).
- 2026-06-12 — Event sourcing + observability SHIPPED (PR #45).
- 2026-06-13 — Phase 8 visiting-agent surface DONE (adx-cli-4).
- 2026-06-13 — Phase 9 Deploy DONE (adx-cli-4).
- 2026-06-13 — Phase 10 Polish & Harden DONE.
- 2026-06-13 — Final Audit COMPLETED clean (Round 1) (adx-cli-4). Verified all 10 phases, ran full test suite (240 passed, 7 skipped), confirmed all deliverables present, and successfully validated all acceptance criteria. Status updated to COMPLETED.

## Failure log

(empty)
