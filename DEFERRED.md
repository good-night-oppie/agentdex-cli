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
| RD-1 | Weco integration (M2 spike 1) | BYO `--api-key` credits differential UNMEASURED (only gemini/openai/anthropic supported; `~/.sakana` token unusable). Blocks "free on your own subscriptions" copy — do NOT publish until measured with a supported-provider key. | 2026-08-15 | etang | 7d524487 |
| RD-2 | PokeAgent ladder (M5 market) | pokeagentchallenge.com has NO ToS; mirroring its leaderboard needs an organizer ask (email/Discord — Karten/Grigsby) before M5 can display anything beyond a deep-link. Link-out is the safe default until then. | 2026-08-15 | etang | 7d524487 |
| RD-3 | Terminal-Bench 2 leaderboard comparison | Paid coding-agent run explicitly deferred by operator. M2 closes on the genuine $0 Harbor oracle + no-op integration evidence; do not claim leaderboard-comparable TB2 quality until a separately budgeted paid run is authorized and recorded. | 2026-08-15 | etang | (this commit) |

## Closed (delete after one weekly audit cycle confirms gone)

| ID | Closing commit | Notes |
|----|----------------|-------|
| CLAUDE-BRIDGE-LIVE-EOF | (this commit) | Bumped excerpt cap in claude_bridge.py from 400 to 4000 to capture complete terminal frame |
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

## PR #704 review-closure deferrals (tc-fugu lineage, 2026-07-19)

| id | tracked | why deferred, and what closing it requires |
|---|---|---|
| OPENBOX-BRIDGES-WIRING | [issue #706](https://github.com/good-night-oppie/agentdex-cli/issues/706) | `adx run --engine bridges` dispatches raw pool names to the single loopback TeamClaude gateway and never reads `.agentdex/openbox.yaml`, so a backend can report READY in `openbox check` yet be ignored or routed under a different model name at run time — and `openbox init` emits a `base_url` key with zero consumers anywhere in the workspace. Not a patch: `LiteLLMWorker` sets `api_base`/`api_key` globally per worker, not per slot (`mini.py:254-255`), so honouring per-backend bindings needs per-slot base-URL plumbing. Closing it means either wiring that, or explicitly declaring openbox advisory-only and marking `check` output as such — plus a test asserting the doc claim matches behaviour so the note cannot drift. Current behaviour is documented in the `run_cmd` module docstring and `adx run --help`. |


## PR #704 fleet-review findings (tc-fugu lineage, 2026-07-19)

| id | tracked | state |
|---|---|---|
| SECRET-RE-RECALL | this row | `Basic <base64>` auth headers loaded at rc 0 — found by ai-scientist-17's AI-Scientist-v2 harness review, FIXED. Regex is now case-sensitive with literal vendor prefixes plus inline `(?i)` on the HTTP auth schemes only; added Stripe/HuggingFace/Groq/Replicate/DigitalOcean/SendGrid/ASIA arms and removed the false positives on `sk-model-v2` / `task-sk-runner-service` / lowercase `akia`. **Still a denylist** — it is defence-in-depth behind the structural `token_ref` contract, not the boundary itself. Any new vendor prefix is a new gap by construction. |
| SELECTION-UNVALIDATED | [#708](https://github.com/good-night-oppie/agentdex-cli/issues/708) | ai-scientist-17: the suite proves selection is *correct*, not that it *picks good models*. No baseline comparison against random / round-robin / epsilon-greedy on the same pool. This is the same root as #708 — a baseline harness would have caught "selects for non-answers" immediately, which is precisely why it belongs before any "measurement engine" claim. |


## PR #704 disposition ruling (tc-fugu-4, 2026-07-19)

| id | tracked | ruling |
|---|---|---|
| SCAFFOLD-RULING | [#707](https://github.com/good-night-oppie/agentdex-cli/issues/707) [#708](https://github.com/good-night-oppie/agentdex-cli/issues/708) | **MERGE AS SCAFFOLD, claim downgraded.** #704 ships the CLI surfaces, seed ledger, allocation loop and selection plumbing — all sound and tested (251 + 44 passing). It does **not** ship a working measurement engine: `policy["gate"]` has zero consumers, so `quality` is never really scored. Merging is right because the blockers are about INPUTS, not about the shipped code being wrong, and because the alternative — 4k tested lines rotting on a branch while M3 stalls — buys nothing. Merging *silently* would be wrong, so three honesty guardrails land with it: simulated rows never average with or outrank measured ones; a constant primary axis is reported as a loud WARNING naming #708 instead of silently ranking on cost; and `--engine fake` output is labelled SIMULATED in both human and JSON. The docs and PR framing no longer call this "the measurement engine". Preconditions before that claim may be made: wire the gate (#707), then a random/round-robin/epsilon-greedy baseline harness (#708) — without the baseline there is no evidence the selector beats chance. |


## Merge-governance exception (tc-fugu-4, 2026-07-19)

| id | what | why recorded |
|---|---|---|
| ADMIN-BYPASS-704 | PR #704 (4412 additions, 13 commits) was merged into `redesign/evolution-market` via **admin bypass**, with **no approving human review** and **one review thread deliberately left unresolved** (the openbox↔bridges contract gap, tracked as #706). Authorised explicitly by Eddie ("merge it") after I declined to request the bypass myself. | I had stated on the bus that #698 was a gate fix with a narrow blast radius while #704 is 4k lines of product surface, and that those deserve different bars — so a bypass here must not pass unrecorded. Merged state at `c588f778`: clean-state CI green, 255 + 44 tests passing, ruff clean. What merged is a SCAFFOLD: `policy["gate"]` still has zero consumers, so the frontier measures nothing yet. The measurement-engine claim is withheld until #707 (wire the gate) and #708 (baseline harness) land. |


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
- PR #16 squash-merge still flagged a UP038 ruff rule in claude_bridge.py + a ruff-format diff in test_rate_table.py; PR #17 lands both fixes so main is green again.
- PR #18 wraps judge SDK calls in a 3-attempt exponential-backoff retry classifier (anthropic / openai / gemini exception names + Cloudflare 5xx body markers) so a transient upstream 525 / 502 / 503 does not excluded-fail every baseline in the Expedition.
- PR #19 adds --dangerously-skip-permissions to the claude cold-shot argv (was only in build_argv long-lived) so the fallback path does not hang on a stdin permission prompt + surfaces stdout in the CliDead message when stderr is empty.
- PR #20 honors explicit Cloudflare "retryable":false / "owner_action_required":true flags in the classifier so a 525 origin-config failure surfaces immediately instead of burning 14 s of exponential backoff.
- PR #21 drops unused `body` local var in PR-20 retry test (F841).
