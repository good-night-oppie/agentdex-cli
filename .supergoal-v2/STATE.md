---
title: State - Agentdex Arena
status: active
owner: etang
created: 2026-06-11
updated: 2026-06-13
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# State: Agentdex Arena — Pokémon Showdown co-opetition platform

**Status:** IN_PROGRESS
**Work queue:** QUEUE_DRAINED (2026-06-12, adx-cli-4) — [Q1] #2 team-draft + #3 break-the-mirror MERGED PR #46 (2ea6dae5); [Q2] #6 sandbox fork + P4 client SQLite local_log MERGED PR #47 (75da5da2); [Q3] BENE PgEngramConnection engram-half adaptor MERGED to bene-main local main (6334fd4 — repo has NO git remote, local branch+full-gate merge is the PR-equivalent; 723 passed + 1 skipped, ruff clean). Next candidates (not queued): re-run 3-agent playtest vs new observability+draft+mirror; #4 archetype gym bots; #8 rated break-mirror w/ i.i.d. defense; mcp_surface.py.
**Current phase:** 10
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
| 10 | Polish & Harden | in_progress | 2026-06-13 | — | Address gaps identified during playtests (e.g. SDK helpers for draft/fork/events, move-level logs in recent_turns/events, etc.). |

## Engineering check status

- Build: green (uv workspace)
- Typecheck: green (mypy via pre-commit)
- Lint: green (ruff + doc-lint 0 BLOCK)
- Tests: 218 pass + 8 gated skips (phase-9 close)

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

- 2026-06-12 — **Phase 8 substrate GREEN (adx-cli-4).** Predecessor (adx-cli-3) left agentdex_arena with 5 failing tests; brought to 8/8. Root causes: (1) gateway hard-called policy(req,ctx) breaking the 1-arg seeded_random anchor → added sim.call_policy public adapter; (2) Starlette TestClient per-request event loop stranded the persistent sidecar → fixture uses `with TestClient` context manager (one loop, matches uvicorn) + create_app lifespan stops sidecar; (3) _advance prompted the visitor on `wait` requests (1..0) → skip them; (4) quota begins piled past sidecar 4-concurrent cap → play-to-end; (5) injection gate counts client-side InvalidURL + route-mismatch 404 as neutralized. Commit fd76db0e.
- 2026-06-12 — **Will Wright × Lilian Weng design synthesis** (workflow wf_7ab43864-fca, 28 agents, 17/20 findings confirmed real, adversarially verified vs live code). Key insight: substrate already ships every Will-Wright-toy brick but the GATEWAY locks them shut — gateway.py:243 mirrors the visitor team onto the opponent (so team_mutation, the only delta-claimable evolution axis, is a NO-OP), gateway.py:210 always faces gym-leader-0, gateway.py:232-244 trusted UN-validated client teams (security gap). 4 fun moves = 4 capability dimensions, each shipped in lockstep with its anti-reward-hack defense. Design note: docs/references/2026-06-12-arena-fun-multidim-rewardhack-design.md (linked from AGENTS.md). Backlog #1 validate-on-begin SHIPPED (commit 1076c333). Remaining #2 team-draft, #3 break-the-mirror (sandbox), #4 archetype gym bots, #5-7 signature vocab, #8 break-mirror rated, #9 held-out-format (new phase 11).
- 2026-06-12 — **Deploy entrypoint + live multi-agent dogfood (PR #44, eac8e3a6).** `python -m agentdex_arena` runnable gateway (single proc, $PORT, file-inbox or webhook OOB owner channel). Dogfood: 3 real agent CLIs — codex/agy/claude(Sonnet) — enrolled, played sandbox gen9 OU, evolved, rematched against a running gateway; harness session logged 13 gaps (docs/references/2026-06-12-arena-playtest-dogfood.md). Agents INDEPENDENTLY reached for #2 team-draft, #3 break-the-mirror, #6 fork, SDK/MCP — real behavior validating the backlog; SonnetBot confirmed failure_signatures accurate. Fixed: G-03 capacity (opaque 400 → retryable 503 + ARENA_MAX_BATTLES=16) + G-04 owner validation ({OWNER} placeholder → 422). cursor-agent quota-blocked (resets 7/9). **Top remaining gap = battle observability**: per-turn state carries no opponent HP + frozen recent-turns (G-01/02/10/11) → agents play blind on the opponent; needs a sidecar.mjs read-only addition (foe HP% + last-turn public events), own focused cycle.
- 2026-06-12 — **Event sourcing + observability SHIPPED (PR #45, 565a70b7).** BENE-Supabase two-tier design (wf_40b7155c-2be, user-ratified): local hash-chain NDJSON = source of truth; Postgres mirror via WriteBehindSync (bounded queue, ON CONFLICT idempotent; dev=adx-pg container :55432, prod=Supabase agentdex.builders pooler — needs project ref + service_role key at deploy). RLS per consent token via session GUC + FORCE RLS + immutable trigger, PROVEN vs PG16. EventLog append O(1) (watermark + stat guard, byte-identity golden). **G-01/02/10 CLOSED with NO sidecar change**: foe HP% + live recent_turns derived from the opponent's own request the gateway already parses; responses carry foe_active/foe_hp_pct/recent_turns. WASM-in-browser REJECTED (design-note appendix): wrong bottleneck/wrong security direction/nothing-to-compile; kernels → P4 local advisory sidecar + future server-side sandbox lane. Tests 201+7. NEXT: P4 client SQLite pull + #6 fork; BENE kernel backend adaptor (bene-main repo, separate PR); re-run 3-agent playtest to verify observability live; #2 team-draft + #3 break-the-mirror.
- 2026-06-13 — **Phase 8 visiting-agent surface DONE (adx-cli-4).** Streamable-HTTP MCP surface tools implemented under /mcp (get/choose/scratchpad/replay/ladder history/evolution diff). Custom lifespan management integrated with the FastAPI parent to propagate lifespan events. Tests (mcp_surface_tools_e2e and mcp_surface_mount) fully verified. PR #50 merged.
- 2026-06-13 — **Phase 9 Deploy DONE (adx-cli-4).** Follow-up PRs #58-#62 merged to main. Ran a 3-agent playtest (OgBot, AgentBot, CodexBot2) in parallel on port 8889. Verified that the draft, sandbox, events, and fork features work end-to-end with the sidecar.mjs changes. All 3 agents reached the `PLAYTEST2_DONE` success terminal signal. Pytest suite clean with 218 passes. Phase 10 (Polish & Harden) active.

## Failure log

(empty)
