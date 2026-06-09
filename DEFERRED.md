# DEFERRED — agentdex-cli phase-8 polish queue

> Closes workflow w0z1i9vcs H2 (deferred-fix tracking) — bd16c47's commit
> body listed SF/D items as "deferred to phase 8" but no tracking artifact
> recorded them anywhere greppable. This file IS the tracking artifact.
>
> Discipline: every entry MUST carry `Until: <ISO-date>` so the weekly
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
| SF5 | `packages/adx_bridges/src/adx_bridges/base.py` `LongRunningCliBridge.send` | workflow w0z1i9vcs codereview-fix-2 review — cost surfaces via instance attr (`bridge.last_cost_usd`) not via published `send()` return tuple. Breaking API change touching base.py + 5 bridges + expedition.py + tests | 2026-07-15 | unassigned | bd16c47 |
| H7 | `cron/weekly_harness_audit.sh` | workflow w0z1i9vcs H7 — audit `check_exists()` is file-presence only. Cannot detect Owner=TODO content drift, past-due `Until:` rows, or orphan doctrine claims (file exists but referenced 0 places) | 2026-07-15 | unassigned | bd16c47 |
| BASELINE-DRIFT | `.secrets.baseline` | PR-O follow-up — `generated_at` timestamp regenerates on every detect-secrets-hook run regardless of code change. CI `pre-commit run --all-files` will surface a baseline-modified exit-3 on every run. Fix: strip `generated_at` post-scan OR swap in `detect-secrets audit` flow | 2026-07-15 | unassigned | 8480584 |
| MOCK-DATA | `tasks/nvidia-earnings-infographic/sources/*.md` | STATE.md Notable event 2026-06-08 — all 4 source MDs carry `# MOCK — replace with live Q3 FY2026 data` markers. BLAKE3 frozen at `9edcd1a12c51f1741d90fab7b733a2144f1831bf7d28a7ead3165052c66dc09c` against MOCK content. Replace + rehash BEFORE any live Expedition run | 2026-07-31 | etang | 1eca32a |
| CALIB-FIXTURES | `packages/agentdex_engine/tests/oracle_calibration_fixtures/` | MF4 + EVAL.md gate — directory + schema scaffolded (README.md), live hand-labeled fixtures land with Phase 6 soft Oracle calibration. ≥10 rows × 2 raters required for κ ≥ 0.7 gate. | 2026-08-15 | unassigned | bd16c47 |
| BRIDGE-SMOKE | `tests/fixtures/bridges/` | MF4 + EVAL.md gate — schema scaffolded (README.md), live captures land with the M6+ live-pool work. `claude_smoke.json` / `codex_smoke.json` / `manus_smoke.json` triple required for the "Subscription-CLI bridge smoke probe passes at session start" criterion. | 2026-08-15 | unassigned | bd16c47 |
| STATE.MD-REFRESH | `.supergoal/STATE.md` | workflow w0z1i9vcs H3 (refuted as spurious live drift but file IS stale) — Current phase: 5 + phases 5/6/7/8 pending. Actual: M3+M4+M5 all shipped (ed4a913 / 22d6285 / bd16c47). `.supergoal/**` deny per `feedback_supergoal_perm_carveout_conflict` memory routes update via human / harness orchestrator. | 2026-07-15 | harness-2 orchestrator | (n/a — no commit; supergoal-mode artifact) |
| AUDIT-OWNER-SCAN | `cron/weekly_harness_audit.sh` | workflow w0z1i9vcs P4 follow-up (paired w/ H7) — restore G13 ep28 [28-0830] citation once sunset-tracking + Owner=TODO scan land | 2026-07-15 | unassigned | 105feb9 |

## Closed (delete after one weekly audit cycle confirms gone)

(none yet — first row to be moved here when its `Until:` passes or
the work lands and a commit closes it)

## Cross-references

- `cron/weekly_harness_audit.sh` §2 doctrine-vs-filesystem cross-check
  SHOULD grep this file for past-due `Until:` dates (post-H7 fix lands)
- `.supergoal/STATE.md` Notable events log captures cross-cutting
  doctrine pivots; this file captures fine-grained deferred-fix
  obligations that don't rise to a Notable event but MUST not be
  silently lost
- `~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_fix_all_before_moving_forward.md`
  — standing policy: when surfacing a ranked-issue list, work the queue
  top-to-bottom; this file is the ranked-issue list for phase-8 polish
