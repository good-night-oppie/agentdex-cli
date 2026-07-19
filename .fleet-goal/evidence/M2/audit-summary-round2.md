---
title: "M2 re-audit round 2 — WU-7..9F landed surface (honesty + adversarially-verified code review)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal/evidence/M2
layer: cross-cutting
cross_cutting: true
---

# M2 re-audit round 2

Workflow `wf_462ffa57-d25` (17 agents: 4 review dimensions ×
adversarial-refutation verify, 1.32M tokens). Range `41f7a1d9..ff88eff7`
(WU-7 context + WU-8/8F HarborCliClient + WU-9 $0 real runs + WU-9F sanitize).
**12 CONFIRMED / 1 refuted.** Same posture as the prior wf_a973b1de-359 gate
audit: a P1 gate bypass of the identical class to the WU-6 P1s was found in
the newly-landed real-engine code.

## CONFIRMED findings (by severity)

### P1 — forgeable reward/cost gate (WU-10 fix dispatched)
- **`_find_trial_result` rglobs the whole trial subtree and trusts any
  agent-writable `result.json`** (`engines/harbor_cli.py:216`). Harbor copies
  the untrusted candidate container's `/logs/artifacts` into
  `<trial>/artifacts/logs/artifacts/` (proven by the WU-9 evidence
  `manifest.json`), which sits under `job_dir` and is walked by `rglob`. A
  candidate plants `result.json` with `task_name` = the requested id,
  `reward=1.0`, `cost_usd=0.0`; with a bare/partial `--harbor-tasks id` the
  genuine verifier file (canonical org-prefixed `task_name`) mismatches and
  falls to `fallback`, while the forged file is the sole `matches[0]` and
  wins → `passed=True` + fabricated measured $0 cost stamped into the Pareto
  receipt. **Corrupts M2's core measured-honesty guarantee.** Fix: read ONLY
  the depth-1 verifier-written `<job_dir>/<trial>/result.json`; never rglob
  the agent-writable subtree. Dispatched as WU-10
  (capsule: wu10-trial-result-path-confinement.md).

### P2 (6) — queued for WU-11 batch
- **Harbor run FAILURE silently reported as genuine quality=0**
  (`harbor_cli.py:169`): nonzero exit / no-artifacts is indistinguishable
  from a real reward-0 run. An infra failure scores as a legitimate
  measurement. Needs an explicit run-status distinct from measured-0.
- **Harbor child process-group leaks on any non-timeout exception during
  wait** (`harbor_cli.py:153`): only `TimeoutExpired` triggers `_kill`; a
  `KeyboardInterrupt`/other exception leaks the group.
- **`--harbor-tasks` missing → exit 1 with internal-API message**
  (`measure_cmd.py:176`), inconsistent with the flag's own exit-2 rejection
  convention.
- **No test covers the harbor-ran-but-no-result path**
  (`test_harbor_cli_client.py:120`) — the exact infra-failure path.
- **tb2-harbor-noop.json receipt cites only ephemeral (gitignored + /tmp)
  artifacts** (`measured/tb2-harbor-noop.json:14`): the durable job copy
  under `measured/wu9-noop-jobs/` exists but the receipt does not point at
  it → a self_reported receipt whose artifacts vanish.
- **arc-local-scripted.json has no in-file signal that quality=1.0 is
  non-leaderboard** (`measured/arc-local-scripted.json:2`): honest in prose
  elsewhere but the artifact itself reads as a clean arc-agi-3 1.0.

### P3 (5) — WU-11 batch / accept-with-note
- Budget/timeout kill does not reap Harbor's detached docker containers
  (`harbor_cli.py:264`) — orphaned paid compute survives SIGKILL; harness
  still stops + reports honestly (cost fallback), so it's a host resource
  leak, not a score spoof. Verifier confirmed harbor's own `delete=true`
  teardown can't finish in the 0.5s grace.
- Default `jobs_dir` is an unmanaged `tempfile.mkdtemp` → receipts reference
  volatile /tmp (`measure_cmd.py:163`). Pairs with the P2 receipt-durability
  finding.
- tb2-harbor-oracle.json `wall_clock_sec=39` not reconciled to a harbor
  artifact timestamp (`measured/tb2-harbor-oracle.json:4`) — cosmetic.
- `--engine-fake` silently overrides explicit `--engine harbor-cli`
  (`measure_cmd.py:93`) — no conflict detection.
- (verification no-defect summary agent — informational.)

## Refuted (1)
- One finding refuted on adversarial re-read (recorded in journal.jsonl).

## Disposition
- **M2 stays OPEN** until the P1 (WU-10) lands + re-verified, then the P2/P3
  hardening batch (WU-11). This is the same "audit found real gate bypass →
  fix before closure" loop that WU-6 ran; the process is working as intended.
- ARC + TB2 genuine-measured-runs evidence legs remain valid (the P1 is a
  forge-path a MALICIOUS candidate could exploit; the WU-9 oracle/no-op runs
  used trusted agents, so their recorded results stand — but the harness must
  be hardened before any untrusted candidate is measured).
