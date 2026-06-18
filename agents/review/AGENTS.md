---
title: agents/review — agentdex-cli
status: active
owner: etang
created: 2026-06-08
updated: 2026-06-18
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# agents/review — agentdex-cli

## Merge philosophy (G2 ep5+7 — async, not sync-block)
- Lint + test gates are MANDATORY but run async — agent can open PR before human looks.
- Canary deploy / preview env runs on every PR; agent watches its own canary metrics.
- Human review is HIGH-LEVERAGE checkpoints (research, plan) not every commit.

## Auto-merge criteria

All criteria below must hold AND the agent's `AUTONOMY_THRESHOLD.md`
gate must be AUTONOMOUS (default SUPERVISED — every PR human-gated
until the 14-day flip gates pass). Until threshold flips, auto-merge
is DISABLED regardless of these criteria.

Scoped by the root [CI-POLICY](../../AGENTS.md#ci-policy): "CI green" /
"hooks pass clean" below mean **your change's own** lint+test job and
**your diff** — a full-tree `pre-commit run --all-files` red on
third-party / sibling-synced files you did not touch (e.g. the
hook-excluded `vendor/aaop/**`) is NOT a blocker; fix such shared red as
its own tiny PR instead of gating yours on it.

- Your change's CI checks green — `uv run --no-sync pytest` over the **changed
  surface** exits 0: the package(s) your diff touches **plus any downstream
  workspace packages that declare them as a dependency** (e.g. editing
  `agentdex_engine` also runs `agentdex_arena`, `agentdex_cli`, `agentdex_plugin`,
  `adx_showdown`). An API/behavior break in a shared package must not pass the gate
  by leaving a dependent's tests unrun. Still not a full blind `packages/` sweep:
  a pre-existing failure in a package neither touched nor downstream of your diff
  is a separate tiny PR, per the CI-POLICY note above.
- No HIGH-severity `agentlint scan` findings (per `agentlint.yaml`)
- `.pre-commit-config.yaml` hooks pass clean **on your diff** — ruff (lint+format),
  mypy (strict on `packages/agentdex_engine/src/agentdex_engine/cards/`),
  detect-secrets vs `.secrets.baseline`
- Coverage delta ≥ 0 (`coverage run -m pytest` vs main baseline)
- Golden Pareto verdict shape still matches
  `tests/golden/nvidia_pareto_expected.yaml` (smoke test invariant)
- Tiny-PR discipline holds: diff touches ≤ 10 files OR commit body
  carries `Note: bundled because <reason>` (per
  `feedback_tiny_pr_discipline` memory + Ideal Moment 1 in
  `IDEAL_EXPERIENCE.md` v2)
- Doctrine anchors green per latest
  `sweeps/<date>-weekly-harness-audit.md` cross-check (10/10 anchors)

## Escalation path

The agent STOPS + pings human when ANY of these triggers fires. The
default `AUTONOMY_THRESHOLD.md` state is SUPERVISED — every PR ALREADY
escalates by default. The triggers below also apply post-flip.

- A planning question genuinely requires user judgment: scope expansion
  beyond the original task, an architectural fork between two equally
  valid approaches, or an irreversible/destructive op (per CLAUDE.md
  "Autonomous-agent defaults" + `feedback_fix_all_before_moving_forward`
  memory). DO NOT escalate "do I batch or split?" — both answers are
  obvious; just work the queue top-to-bottom.
- HIGH-severity `agentlint scan` finding lands on main (per
  `AUTONOMY_THRESHOLD.md` rollback trigger).
- Eval golden set score drops > 5% in a single PR.
- Pre-commit `detect-secrets` flags a NEW result not present in
  `.secrets.baseline` — likely real leak; do not auto-rebase the
  baseline.
- An issue requires credentials, external account access (Anthropic
  console billing, GH org admin), or capabilities the agent lacks.
- The agent has edited the same file > 5 times in one session AND
  tests still fail — doom-loop guard per `agents/debug/AGENTS.md`
  G4 LangChain ep4 trigger.

Ping channel: append a one-line entry to
`~/.cursor/projects/home-admin/heartbeat/monitor-gaps.md` (the same
gap log the cron wrappers funnel into); the persistent orchestrator
(`harness-N` per `feedback_persistent_orchestrator` memory) sweeps
that file on its 1h gap-log cadence.
