---
title: "agentdex-redesign PROTOCOL (orch-proj state)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

# PROTOCOL — agentdex-redesign-evolution-market run

## Evidence-before-completion
A milestone may be marked done ONLY after:
1. every evidence item for it exists under `.fleet-goal/evidence/M<N>/`;
2. a fresh/independent thread's 5-question audit returned "complete + next goal right";
3. `/review` (or `/code-review`) ran on the milestone's diff (findings fixed or waived in evidence).

## Failure protocol
- A failed check: fix and re-run, up to 3 materially-varied attempts.
- Still failing: write `.fleet-goal/audit-fix-<round>.md` (what failed, hypothesis, fix
  plan), execute it, re-verify.
- Genuine scope / credentials / architecture fork: hand back to the user and stop.

## Protected paths (READ-ONLY)
- <paths that must never be created/edited/deleted by this run>
- Every subagent prompt restates these as READ-ONLY and reports mismatches as findings,
  never edits them.

## Coordinator discipline
- Main thread holds objective / constraints / decisions / state only.
- Delegate greps, refactors, audits, reviews to subagents/threads.
- Workers return four fields: what was learned / what changed / supporting evidence /
  what should happen next. Never full transcripts.
- Report only What's done / What's next / Any blockers on state change; keep PROGRESS.md current.

## Environment-bound tests
- Browser / desktop app / permissions / credentials / device-state checks run on the
  local thread, never inferred from files.

## Model routing (adapt to the environment's aliases)
- Coding / implementation / greps / mechanical evidence -> cheap coding worker (e.g. `coco`).
- Orchestration / planning / design / triage / review / audit -> reasoning agent (e.g. `fugu`).
- Audit and review subagents specifically run as `fugu --yolo`.
- An implementer never audits or reviews its own output.
