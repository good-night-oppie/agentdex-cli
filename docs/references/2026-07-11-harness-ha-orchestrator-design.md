---
title: Harness HA orchestrator design
status: draft
owner: etang
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: docs/references
layer: cross-cutting
cross_cutting: true
---

# Harness HA orchestrator design

## Decision summary

Do not build a custom three-node leader-election or consensus protocol inside
Harness. Use Temporal OSS as the durable execution authority and run
`harness-<number>`, `harness-<number>a`, and `harness-<number>b` as replaceable
workers polling one control-group task queue.

Bene remains the communication and coordination-audit surface. Temporal owns
workflow progress, retries, task ownership, timers, and crash recovery. External
effects remain idempotent because Temporal Activities may be retried.

## Target architecture

```text
                    Operator
                       |
                       v
               Bene durable A2A bus
             communication + audit log
                       |
                       v
              A2A -> Temporal bridge
                       |
                       v
             Temporal Workflow Service
          durable history + task ownership
                       |
             task queue: harness-control
          +------------+-------------+
          |            |             |
          v            v             v
   harness-N     harness-Na     harness-Nb
   worker        worker         worker
```

There is no application-level primary to fail back to. Only the worker holding
the current Temporal task may execute the corresponding step. A returning
worker resumes polling and does not preempt active work.

## Model-cost policy

Use the `warm state, cold inference` pattern. Secondaries stay operationally
warm by replaying durable events, verifying hashes, maintaining caches, and
checking health, but they make no routine LLM calls.

```text
STANDBY
  deterministic only; no LLM
     |
     | optional sampled audit
     v
OBSERVER
  cheap or local model; strict budget
     |
     | exclusive Temporal task + model grant
     v
PRIMARY_WARMUP
  load checkpoint; start frontier model
     |
     | readiness probe passes
     v
PRIMARY
  frontier model authorized for hard decisions
     |
     | task loss or handoff
     v
DEMOTING
  checkpoint; revoke model grant; return to standby
```

Promotion to a frontier model must follow authoritative Temporal task ownership,
not an instance's local belief that it is primary. A deterministic model-admission
grant binds the control group, worker identity, Workflow run, task token, model
class, expiry, call budget, and token budget.

Use three inference tiers:

1. deterministic: state replay, registry validation, health checks, PR polling,
   idempotency checks, and policy gates;
2. cheap/local: event-delta summaries, anomaly classification, sampled audits,
   and low-risk ranking;
3. frontier: code changes, architecture decisions, conflicting evidence, and
   operator-facing authority decisions.

Within the active worker, use a cascade:

```text
deterministic gate -> cheap model -> validator
                                      |
                         uncertain or high-risk
                                      |
                                      v
                                frontier model
```

## Idempotency boundary

Every external mutation uses a stable key derived from the Workflow and logical
target, for example:

```text
harness-control/harness-41:merge-pr:good-night-oppie/bene#147
```

The target-side command journal follows this contract:

```text
same key + same payload      -> return the recorded result
same key + different payload -> reject an idempotency conflict
new key                      -> execute and record atomically
```

Candidate Activities include `ReadFleetState`, `RunFleetDoctor`,
`SendA2AMessage`, `DispatchCapsule`, `CreatePullRequest`, `CheckPullRequest`,
and `MergePullRequest`.

## OSS grounding

- [Temporal task queues](https://docs.temporal.io/task-queue) support multiple
  workers polling one queue and task routing between workers.
- [Temporal architecture](https://docs.temporal.io/evaluate/understanding-temporal)
  persists Workflow event history for replay and recovery.
- [Temporal Activity guidance](https://docs.temporal.io/activity-definition)
  requires idempotent business Activities because retries can execute them more
  than once.
- [Kubernetes client-go leader election](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection)
  explicitly does not guarantee fencing, so a Kubernetes Lease alone is not a
  sufficient external-side-effect boundary.
- [Argo Workflows HA](https://argo-workflows.readthedocs.io/en/latest/high-availability)
  is a credible alternative when all actions are Kubernetes pods, but it is a
  poorer fit for native authenticated interactive tmux workers.
- [LiteLLM routing](https://docs.litellm.ai/docs/routing) provides an OSS model
  gateway pattern for routing, fallback, rate awareness, and accounting.
- [RouteLLM](https://github.com/lm-sys/routellm) demonstrates strong-versus-weak
  model routing. Any threshold must be calibrated on Harness tasks rather than
  copied from general benchmarks.

For native subscription-authenticated Codex or Claude sessions, apply model
policy in the launcher. Do not send native subscription traffic through a
third-party reverse proxy.

## Incremental migration

Use a strangler boundary so Agentdex redesign work continues:

```text
existing operation
      |
      +-- not migrated --> current implementation
      |
      +-- migrated -----> Temporal Workflow or Activity
```

Migrate in increasing risk order:

1. read fleet state;
2. run fleet doctor;
3. send an idempotent A2A message;
4. acknowledge an escalation;
5. dispatch a capsule;
6. create and monitor a pull request;
7. merge a pull request;
8. perform a runtime handoff.

## Estimated wall-clock schedule

With one dedicated infrastructure lane operating alongside the Agentdex redesign
lane:

| Outcome | Estimate |
|---|---:|
| Working HA proof | 4-6 working days |
| Useful production path | 10-15 working days |
| Hardened migration and soak | 3-4 calendar weeks |

Suggested checkpoints:

```text
Day 2: Temporal running in development
Day 5: two LLM-free secondaries visible and healthy
Day 7: demonstrated worker-failure recovery without duplicate effects
Week 2: main fleet operations migrated
Week 3: model admission and controlled frontier promotion
Week 4: soak complete and legacy ownership retired
```

The Day-7 go/no-go gate is deterministic recovery without duplicated external
effects. If that proof fails, stop the migration and keep Agentdex on the current
controller while the failure is resolved.

## Non-goals

- Replacing Bene as the human and agent communication ledger.
- Running native interactive subscription sessions inside disposable pods.
- Inventing a Harness-specific consensus algorithm.
- Migrating all fleet operations in one release.
- Keeping frontier-model contexts continuously active on secondary workers.
