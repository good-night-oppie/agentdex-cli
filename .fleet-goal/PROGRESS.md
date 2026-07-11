---
title: "agentdex-redesign PROGRESS (orch-proj state)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

# PROGRESS — agentdex-redesign-evolution-market

## M1 — research + architecture design (audit PASS / review findings remediated)

### What's done

- 6-lane research sweep + gap critic (evidence/M1/research/, lane-label rotation fixed per audit P2).
- User decisions recorded verbatim in GOALS.md: supersession, MVP order, two-class ladder taxonomy (+PokeAgent, diligence PASS incl. authenticated Playwright login — team AgentDex, bot adx-bot-1), 3-layer loop (weco drives, mh gates), v1 adapters ARC-AGI-3+TB2+PokeAgent, no-Fable-coding/mroute routing.
- DESIGN.md + ADR-0015 draft + M2-M6 roadmap; PokeAgent gate class pinned (D4a, open-ELO w/ opponent-mix guard, A2A #2622/#2623 answered).
- Fresh audit (5-question) PASS + evidence-grounding review: P1 (collaborative-path promotion qualifier) and all P2/P3 findings remediated in-place; weco-start-claude primary-source snapshot captured.

### What's next

- (done) M1 CLOSED 2026-07-11 — user confirmation verbatim in evidence/M1/user-confirmation.md.

## M2 — Pareto measurement engine [ACTIVE]

### What's done

- Standing principle + pre-run validation gate recorded (GOALS M2, user directive: gate scores the REAL objective, not a proxy; s14 anti-precedent).
- WU-1 DONE + committed (c5929485): packages/adx_frontier — AgentCandidate manifest + pre-run validation gate (weco --sources limits, budget, axes partition); 13 tests, independently re-run by coordinator; served by grok-4.5 tier.
- WU-2 DONE + committed:  packages/adx_ladders — LadderAdapter ABC (two-class taxonomy, Receipt tier rules, MeasureResult axes enforcement, pre_run_check) + curated market registry (6 ladders + HF substrate, link-out only). Capsule: evidence/M2/capsules/wu2-ladder-adapter-registry.md.

- WU-3 DONE + committed (84a7c435): arc_agi3 out-of-process adapter — stdio JSON protocol, budget-kill honesty (quality=0, never dropped), D6 receipt branching; 34 tests total, coordinator re-verified.
- WU-4 dispatched (mroute execute): tb2_harbor static-class adapter — HarborProtocol injected, equal-split per-task timeouts, always self_reported receipts w/ per-task summary JSON for M3's decontam gate. Capsule: evidence/M2/capsules/wu4-tb2-harbor-adapter.md.
- Fleet coordination: rpo-addressed A2A handled as parent (rpo idle-done) — ai-scientist's s14 ladder-probe proposal answered DO-NOT-SUBMIT (operator's s14 anti-precedent statement on record); mroute adoption feedback sent (using=yes freq=often).

- WU-4 DONE + committed (be46e1cd): tb2_harbor static-class adapter.
- WU-5 DONE + committed: `adx measure` CLI verb — M2's headline outcome now runs end-to-end (fake engines, hard-fenced receipts); 44 tests, coordinator-verified incl. live invocation.
- Spikes 3 (ToS) + 5 (arXiv) running as a research Workflow (wf_93d1700c-fd5).

- Spikes 2/3/4/5 DONE (evidence/M2/): ToS per-source verdicts; 8/8 arXiv VERIFIED; mixed-direction frontier native (+mean/sum aggregation pinned); fourth adapter = SWE-Bench Pro @ N=10.

- Spike 1 DONE (operator authenticated a fresh account): grant 20 credits, $0.17/3-step toy, per-step transparent billing; `weco start claude` + `weco share` verified; BYO differential unmeasured (supported providers gemini/openai/anthropic only). All five M2 spikes closed.

### What's next

- Run the fresh independent M2 five-question audit + code review against the final head and genuine no-cost receipts.
- Close M2 only if both gates pass; then activate M3. Paid leaderboard-comparable TB2 remains tracked as RD-3 and is not an M2 closure gate.
- Publish the accumulated redesign work as bounded logical PRs and babysit each to MERGED before M3 implementation.

### Any blockers

- None. The operator selected the no-spend path: existing genuine ARC + real-Harbor oracle/no-op TB2 receipts satisfy M2's integration-evidence gate; paid leaderboard-comparable TB2 is deferred as RD-3.

### harness-41 session (2026-07-11) — review queue + real-engine wiring

- Reaped predecessor (harness-40 tmux session killed, operator-authorized). Fleet-enrolled harness-41 (A2A base `harness`; enroll intent shared_log#2655; watch-coverage renew #2657; base already ON_BUS + WATCHED).
- Cleared the 4 remaining review-queue findings, each a tiny mroute-dispatched commit (grok-4.5 exec tier), coordinator-reviewed + tested + pushed:
  - [P2] measured-cost honesty — `MeasureResult.cost_is_measured` bool; ARC/TB2 declared-budget fallback → False, measured/override → True; serialized in `adx measure` JSON + adapter run-logs. (commit c69d0c4a)
  - [P3] registry↔KNOWN_LADDERS now asserts set equality both ways. (commit a71b16f7)
  - [P3] candidate glob/name hardening — empty/missing mutable, zero-match glob, and invisible-Unicode (Cf) names now fail closed. (commit 378a1ef2)
  - [P3] SWE-Bench Pro registry note refreshed (stale "Fourth-adapter slot TBD" → spike-2 "SWE-Bench Pro @ N=10"). (commit c4404234)
- [WU-7] Real-engine wiring (free leg): genuine local ARC-style engine (`adx_ladders/engines/local_arc.py`, action-dependent dynamics, scorecard_id→None), scripted-heuristic no-LLM candidate, `adx measure --engine local-arc`. First GENUINE MEASURED run recorded: `.fleet-goal/evidence/M2/measured/arc-local-scripted.json` (quality=1.0, cost_dollar=0.0, cost_is_measured=true, receipt self_reported/raw_artifacts — NOT fake_engine, honestly non-leaderboard). 78 tests green. (commit 3f1c0581)
- [WU-8+8F] Real Harbor CLI client (free leg, mroute execute grok-4.5 tier): `adx_ladders/engines/harbor_cli.py` grounded in INSTALLED harbor 0.18.0 (verbatim surface capture at evidence/M2/harbor-cli-surface.md — real docs drift found: `-i/--include-task-name`, `--agent-import-path` deprecated → `-a module:Class`, no per-dataset task-list subcommand → injected `tasks=` fallback); WU-6 kill idioms (DEVNULL stdin, start_new_session, group SIGTERM→SIGKILL, fork-based SIGTERM-ignoring grandchild reap tests); `adx measure --engine harbor-cli` wired. Coordinator review found 3 defects, fixed via WU-8F capsule: F1 P1 pipe-full deadlock (undrained PIPEs + bare wait misreport chatty PASSING runs as timed_out — read-side twin of WU-6 stdin P1; fixed with on-disk harbor.log redirect + >128KB regression), F2 `-l 1` hard task cap (`-i` accepts globs; `-n` is concurrency), F3 measure-time ValueError traceback (now clean stderr + exit 1). 184 tests green (was 173; the 1 expedition-smoke failure verified PRE-EXISTING on origin/main — out of diff scope per standing policy). NO paid run executed. Follow-up: CLI `tasks=` injection path (WU-9 with the $0 real run).

### Paid TB2 disposition (resolved)

- Operator decision, 2026-07-11: no spend. Accept the genuine ARC run plus real-Harbor oracle/no-op TB2 runs as M2 integration evidence; defer any paid leaderboard-comparable TB2 quality claim to RD-3.
- **M2 RE-AUDIT round 2 (wf_462ffa57-d25, 17 agents, 1.32M tok): 12 CONFIRMED / 1 refuted — including a P1 gate bypass of the SAME class as the WU-6 P1s.** evidence/M2/audit-summary-round2.md. ALL 12 NOW RESOLVED:
  - [WU-10] P1 forgeable reward/cost gate (`_find_trial_result` rglob'd the whole trial subtree; Harbor copies the untrusted candidate container's `/logs/artifacts` in, so a candidate could plant a forged reward=1.0/cost=$0 file and forge a MEASURED pass). Fixed by PATH-CONFINEMENT: read only the depth-1 verifier-written `<job>/<trial>/result.json`, never the agent-writable subtree. Adversarial repro PROVEN (test fails on old rglob impl: passed=True/cost=0.0 into `.../artifacts/logs/artifacts`). commit a1f7edbe.
  - [WU-11] P2 #9 infra-failure-≠-measured-0 (harbor nonzero-exit/no-trial-result now `errored`, EXCLUDED from pass_rate denominator, forces cost_is_measured=False) + P2 #6 PG-leak-on-non-timeout-exception (`except BaseException: _kill; raise`). Both repro-proven. commit c32cb5ec.
  - [WU-12] P3 #11 `--engine-fake` silent override of explicit `--engine` (now exit-2 conflict) + P2 #10 `--harbor-tasks`-missing exit-code consistency (exit 2 up front) + P2 #3/P3 #7 durable `--jobs-dir` so receipts cite stable artifacts. Repro-proven. commit d3a28400.
  - ACCEPT-WITH-NOTE (rationale recorded): P2 #4 arc-local non-leaderboard signal (receipt `tier=self_reported` + empty `ref` ALREADY encodes non-leaderboard per the two-tier taxonomy; hand-editing measured artifacts = evidence-tampering, refused); P3 #5 oracle wall_clock reconcile (cosmetic); P3 docker-orphan-on-kill (host resource leak, harness still stops+reports honestly — not a score spoof); P3 #8 (informational no-defect summary).
  - Each fix landed via mroute execute + coordinator review + INDEPENDENT fail-on-old/pass-on-new reproduction (same audit→fix→reverify loop as WU-6). WU-9 oracle/no-op evidence stands (trusted agents); the harness is now hardened for untrusted candidates.
  - **FIX-REGRESSION CHECK (wf_e12e9a0c-2e5, 6 agents): WU-10 + WU-11 CLEAN; caught ONE new P2 the WU-12 fix introduced** — the new `--jobs-dir` flag crashed with a raw traceback on a bad path (mkdir OSError not caught), violating the CLI's never-a-traceback contract. Fixed [WU-12F] (OSError guard → exit 2), repro-proven. commit 064fae2a. This is the fix-introduces-bug tail the reverify pass exists to catch. The former paid-TB2 fork is resolved by the no-spend RD-3 disposition above.
- Free legs DONE (2026-07-11, harness-41 cont.): [WU-8+8F] real `HarborCliClient` LANDED. [WU-9] $0 GENUINE real-Harbor runs LANDED: oracle leg on real task `terminal-bench/regex-log` (passed=true, reward 1.0, 39s, real Docker env — engine-integration evidence, `evidence/M2/measured/tb2-harbor-oracle.json`) + no-op candidate leg through the full `adx measure → Tb2HarborAdapter → HarborCliClient` stack (honest quality=0.0, self_reported/raw_artifacts receipt, real job artifacts — `tb2-harbor-noop.json`). Both adapters now have genuine measured integration runs. [WU-9F] org/name→*name filename sanitization fix LANDED at ff88eff7.
