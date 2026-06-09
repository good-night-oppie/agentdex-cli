---
title: DEFERRED — agentdex-cli phase-8 polish queue
status: active
owner: etang
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# DEFERRED — agentdex-cli phase-8 polish queue

> Closes workflow w0z1i9vcs H2 (deferred-fix tracking) — bd16c47's commit
> body listed SF/D items as "deferred to phase 8" but no tracking artifact
> recorded them anywhere greppable. This file IS the tracking artifact.
>
> Discipline: every entry must carry `Until: <ISO-date>` so the weekly
> harness audit can flag past-due items (per IDEAL_EXPERIENCE.md anti-fire-
> exit clause + the `feedback_fix_all_before_moving_forward` memory). When
> an item lands, delete its row + record the closing commit hash in
> `sweeps/<date>-weekly-harness-audit.md` §5 action queue.

## Format

```
| ID | Surface | Cited finding | Until | Owner | Open commit |
|----|---------|---------------|-------|-------|-------------|
```

## Open

| ID | Surface | Cited finding | Until | Owner | Open commit |
|----|---------|---------------|-------|-------|-------------|
| MOCK-DATA | `tasks/nvidia-earnings-infographic/sources/*.md` | STATE.md Notable event 2026-06-08 — all 4 source MDs carry `# MOCK — replace with live Q3 FY2026 data` markers. BLAKE3 frozen at `9edcd1a12c51f1741d90fab7b733a2144f1831bf7d28a7ead3165052c66dc09c` against MOCK content. Replace + rehash BEFORE any live Expedition run | 2026-07-31 | etang | 1eca32a |
| CALIB-FIXTURES | `packages/agentdex_engine/tests/oracle_calibration_fixtures/` | MF4 + EVAL.md gate — directory + schema scaffolded (README.md), live hand-labeled fixtures land with Phase 6 soft Oracle calibration. ≥10 rows × 2 raters required for κ ≥ 0.7 gate. | 2026-08-15 | unassigned | bd16c47 |
| STATE.MD-REFRESH | `.supergoal/STATE.md` | workflow w0z1i9vcs H3 (refuted as spurious live drift but file IS stale) — Current phase: 5 + phases 5/6/7/8 pending. Actual: M3+M4+M5 all shipped (ed4a913 / 22d6285 / bd16c47). `.supergoal/**` deny per `feedback_supergoal_perm_carveout_conflict` memory routes update via human / harness orchestrator. | 2026-07-15 | harness-2 orchestrator | (n/a — no commit; supergoal-mode artifact) |

## Closed (delete after one weekly audit cycle confirms gone)

| ID | Closing commit | Notes |
|----|----------------|-------|
| BRIDGE-SMOKE-part-1 | 38b23e7 (PR-T) | capture script + validator test landed; live captures still pending (part 2) |
| CALIB-FIXTURES-part-1 | 553ebd4 (PR-U) | 13 hand-labeled rows + round-trip test; full κ ≥ 0.7 inter-rater pending second labeler |
| M7-scaffold | (this PR) | LearnedSeedGenerator Protocol + RecurrencePatternGenerator placeholder + merge helper; real ML post-M9 helios |
| SF5 | phase-8/sf5-bridge-response-class | `BridgeResponse` dataclass returned by `send()` carries `text`/`langfuse_trace_id`/`cost_usd`/`tokens`; orchestrator + 5 stubs migrated off the `getattr(bridge, "last_cost_usd")` back-channel; legacy properties retained for ad-hoc debug |
| H7 + AUDIT-OWNER-SCAN | phase-8/h7-audit-content-scan | weekly audit §2c Owner=TODO scan + §2d orphan doctrine anchor scan (basename-grep heuristic) landed; G13 ep28 [28-0830] sunset citation restored in script header (replaces the pruned TODO comment) |
| BASELINE-DRIFT | phase-8/baseline-drift | `scripts/detect_secrets_no_drift.sh` wraps `detect-secrets-hook`, strips `generated_at`, suppresses exit-3 when timestamp was the only diff; pre-commit hook swapped to local `language: system` entry point. True-positive findings (rc=1) still propagate; verified w/ injected AWS-key fixture |
| BRIDGE-SMOKE | phase-8/bridge-smoke | All 3 live captures (claude/codex/manus) recorded via `tools/agent_senses/capture_bridge_smoke.sh` against installed CLIs; validator (`test_bridge_smoke_fixtures.py`) green for all 3. EVAL.md "Subscription-CLI bridge smoke probe passes at session start" criterion now enforceable on every push |

## Cross-references

- `cron/weekly_harness_audit.sh` §2 doctrine-vs-filesystem cross-check
  SHOULD grep this file for past-due `Until:` dates (post-H7 fix lands)
- `.supergoal/STATE.md` Notable events log captures cross-cutting
  doctrine pivots; this file captures fine-grained deferred-fix
  obligations that don't rise to a Notable event but must not be
  silently lost
- `~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_fix_all_before_moving_forward.md`
  — standing policy: when surfacing a ranked-issue list, work the queue
  top-to-bottom; this file is the ranked-issue list for phase-8 polish
