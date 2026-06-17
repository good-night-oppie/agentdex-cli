---
title: "ADR-0012: Arena partitioning + scale to ~100 concurrent — battle_id is the partition key"
status: active
owner: "@EdwardTang"
created: 2026-06-17
updated: 2026-06-17
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "§4.1 a battle is a deterministic state machine — outcome is a pure function of (seed, inputLog); turns advance in lockstep with no arrival races"
    test: "packages/adx_showdown/tests/test_sidecar_sim.py"
  - claim: "§4.3 the EventLog is the source of truth; the ladder is a DERIVED view that recomputes from the log byte-identically (CQRS read model)"
    test: "packages/agentdex_arena/tests/test_q5_anti_pay_to_rank_property.py"
  - claim: "§4.3 events mirror to Postgres via idempotent log-shipping; a replayed/re-synced chain is a no-op; a PG outage degrades to mirror-lag, not data loss"
    test: "packages/agentdex_arena/tests/test_eventsync.py"
  - claim: "§4.2 durable append is fail-closed and happens BEFORE the battle advances (WAL discipline) — a crashed append stops the sidecar, never acks a lost turn"
    test: "packages/agentdex_arena/tests/test_receipt_atomicity.py"
---

# ADR-0012: Arena partitioning + scale to ~100 concurrent

**Amends/extends** [[0010-arena-repromotion]] (Showdown lane) and the deploy go/no-go
(`docs/references/2026-06-11-arena-deploy-gonogo.md`).

## Context

The arena today is a **single FastAPI service + single sidecar** (one Node process
multiplexing `BattleStream`s, `ADX_SIDECAR_MAX_BATTLES` default 4) on a 256 MB ai-builders
nano. Measured: sidecar 55 MB idle → 178 MB first battle (engine load) → +~3.5 MB/battle;
~3 concurrent battles is the safe ceiling at 256 MB. We need a documented architecture for
**~100 concurrent real users** (and eventually PvP), and a decision on the **partition key**
before building a sidecar pool.

Pokémon Showdown (vendored, 0.11.10) ships two execution models; the arena deliberately uses
the lighter **sim-as-library** path (ADR-0010 F1): `new BattleStream()` per battle, many
multiplexed in one process (`packages/adx_showdown/sidecar.mjs`), **not** the stock
one-subprocess-per-battle server (~599 MB). Load-bearing engine properties we build on:
`prng.ts` — `(seed + inputLog)` fully reconstructs any battle (the inputLog is a per-battle
WAL of choices); `sim/state.ts` `State.serializeBattle/deserializeBattle` — a live battle is
snapshottable; the sidecar drives choices in **lockstep** (`step {choices:{p1,p2}}`,
per-side `pending`/`submitted`) so turn resolution is deterministic and race-free.

Turn resolution is **sub-millisecond and I/O-bound on agent decisions** (the LLM call per turn
takes seconds; the sim idles between turns). So node being single-threaded is **not** the
bottleneck — memory per battle, the LLM-decision fan-out, and log-append throughput are.

## Decision

1. **Partition the arena by `battle_id`.** A battle is simultaneously the unit of *state* (the
   whole `Battle` object + its per-battle PRNG), the unit of *computation* (a turn reads/mutates
   only that battle), and the unit of *consistency* (a turn is atomic, serialized by the battle's
   single owner). These coincide → battles are **share-nothing**: two battles never read/write
   each other, never lock, never coordinate. Adding capacity is linear, coordination-free.

2. **One battle lives on exactly one sidecar = single-writer per partition.** Turn resolution is
   a **local** transaction (collect choices → `step` → advance), never a distributed one.

3. **Scale the sim tier as a `SidecarPool`** (replaces the single `sidecar_factory`): K node
   processes across cores, each capped at a *measured* per-process battle count; the gateway
   becomes a partition-aware router holding a `battle_id → sidecar` map. `/battle/{id}/choose`
   routes to the owning sidecar.

4. **Multiplayer (2–4 users/battle) routes by `battle_id`, NOT `user_id`.** All of a battle's
   players land on the one owner so turn resolution stays local. Partitioning by `user_id` would
   scatter a battle's sides across partitions and make **every turn a distributed transaction** —
   rejected. The engine already supports N independent choosers (per-side `pending`/`submitted`);
   today p2's choice comes from a server-side house bot, in PvP it arrives from a second user's
   `/choose` — same data plane, different source.

5. **Crash recovery uses the WAL we already have.** Resurrect an in-flight battle by replaying
   `(seed, inputLog)` on any pool member, or restore from a periodic `State.serializeBattle`
   snapshot (checkpoint + WAL-tail). Removes today's "sidecar crash = lost battle" fragility.

6. **Ladder stays a derived materialized view, made incremental.** Keep event-sourcing
   (EventLog = source of truth, Postgres mirror via idempotent log-shipping). Fold each
   `battle-result` event into a `ratings` table (streaming view) + cache `/ladder`; full
   `recompute_ladder()` replay becomes the rebuild/repair path only.

7. **Admission control, not thrashing.** Pool capacity = Σ sidecar caps; over it → bounded queue
   + `503` + `Retry-After`; per-owner concurrency cap; keep the LLM `BudgetGuard`.

8. **Keep cross-partition work off the per-turn hot path.** Ratings aggregation and matchmaking
   are global, but both happen *off* the turn loop (result-emit at battle end; matchmaking at
   battle creation) → the partition stays share-nothing.

## Rationale (DDIA framing)

The arena is a **partitioned, event-sourced, deterministic state-machine** system. What it
already embodies correctly: event sourcing (append-only EventLog, `local_log.py`); async
replication / log-shipping with idempotent catch-up (`eventsync.py`); CQRS derived read model
(`recompute_ladder`); WAL discipline (`_append_or_fail_closed` durably appends *before*
advancing); state-machine replication (`seed+inputLog` replay, `/replay` `/fork` `/dispute`).
The only real gaps for 100-concurrent are **partitioning the sim tier** and **closing the
in-flight-battle recovery gap** — both cheap *because* battles are share-nothing and
deterministic.

Why `battle_id` and not `user_id`: a good partition key co-locates the unit of consistency with
the unit of computation so a request never crosses partitions on the hot path. `battle_id` does;
`user_id` does not (a 2–4-player battle's sides would split across partitions). Multiplayer is the
strongest argument *for* `battle_id`.

## Consequences / to build (target — not yet implemented)

- `packages/adx_showdown/`: `Sidecar` → `SidecarPool` (spawn K, route by battle, per-proc cap);
  add `snapshot`/`restore` commands to `sidecar.mjs` (engine already supports it).
- `gateway.py`: `battle_id → sidecar` routing map; pool-aware capacity + bounded queue;
  per-owner cap; incremental rating fold + cached `/ladder`.
- PvP additions (all *within* the partition, not partitioning): simultaneous-choice turn sync
  (wait for all sides before `step`), per-turn timeout → auto-forfeit, per-user→side auth + the
  Showdown SECRET/OMNISCIENT view split (no peeking), and a separate off-path **matchmaking
  queue**.
- Durability: SQLite EventLog in WAL mode + batched appends (`_append_many_or_fail_closed`);
  measure append rate at ~100×turns/s; keep the async PG mirror (eventual consistency for the
  leaderboard is correct).
- Platform: leave the 256 MB nano (it cannot do 100 concurrent) for a multi-core instance with
  scale-to-zero disabled, or a horizontally-scaled host.

## Must-measure before sizing (cannot be derived)

1. Per-sidecar ceiling: RSS + turn-resolution p95 as concurrent battles climb → battles/sidecar.
2. Append throughput: SQLite-WAL vs Postgres-direct at ~100×turns/s.
3. LLM-decision fan-out vs the platform proxy rate/budget at 100 concurrent.

Expected bottleneck order: **LLM tier first, sim-memory second, sim-CPU never.**
