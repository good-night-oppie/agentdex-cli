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
| CALIB-FIXTURES | phase-8/calib-rater2 | Rater-2 sidecar (`labels_rater_2.yaml`) lands AI-judged labels for all 13 fixtures; `test_inter_rater_kappa.py` asserts Cohen's κ ≥ 0.7 gate (current value 0.846 — 1 marginal disagreement on `nvidia-mixed-format`). Rater-2 is documented as AI by design; promote to human rater-3 when one is available (queue under CALIB-RATER-3 at that point) |
| STATE.MD-REFRESH | phase-8/state-md-refresh | `.supergoal/STATE.md` refreshed in-place per session-2 user authorization ("do 1 to 3 to unblock"); content now reflects M0–M5 done, phase-8 active, the 6 session-2 PRs, and 95 pass + 7 skip test signal. `.supergoal/**` is gitignored so the refresh itself is local-only — this PR carries the DEFERRED row close + a memory-drift note. The `feedback_supergoal_perm_carveout_conflict.md` claim was stale; `echo "test" >> .supergoal/STATE.md` returned rc=0 in session 2 — perm rules now allow Bash-redirect writes |
| MOCK-DATA | phase-8/mock-data-live-q3 | All 4 source MDs rewritten with live Q3 FY2026 results (quarter ended 2025-10-26; released 2025-11-19) + DOC-LINT-010 frontmatter added. New BLAKE3 = `2f3bf8fee53690f76e4701a5097aabb3e19f5bb146a136fe95a2b8d7169c3346` (was `9edcd1a1...`). `bundle.yaml` rehashed + 5 test files (`test_expedition.py` / `test_polish.py` / `test_calibration_fixtures.py` / `test_oracle.py` / `test_balancer.py`) updated to match. Headline numbers: revenue $57.0B (was $35.08B), Data Center $51.21B (was $30.77B), GAAP margin 73.4% (was 74.6%), Q4 guide $65.0B (was $37.5B). `expeditions/*/task_card.yaml` historical records intentionally NOT updated — those are frozen run snapshots, not part of the canonical bundle. 95 pass + 7 skip unchanged |

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

## Session 2 lint follow-ups (post-DEFERRED-drain)

- PR #15 squash-merged with an unused SimpleNamespace import the CI flagged after-the-fact; PR #16 drops it. Doc-lint pairing for the import-drop lives in this note.
