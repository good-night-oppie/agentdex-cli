---
title: "BENE-Supabase event sourcing — two-tier battle observability (server Postgres / client SQLite)"
status: active
owner: "@EdwardTang"
created: 2026-06-12
updated: 2026-06-12
type: reference
scope: packages/agentdex_arena
layer: data
cross_cutting: true
enforced_by:
  - "packages/agentdex_arena/tests/test_eventsync.py (RLS isolation, immutable trigger, idempotent mirror, migration-DDL parity)"
  - "packages/agentdex_engine/tests/test_arena_instrument.py (O(1) watermark byte-identity, two-writer guard, unknown-type recompute)"
  - "packages/agentdex_arena/tests/test_visitor_surface.py::test_battle_observability_foe_hp_and_recent_turns (G-01/G-02/G-10)"
---

> **Provenance.** Synthesized by workflow `wf_40b7155c-2be` (11 agents; 3 design areas each adversarially verified — every verifier objection folded into this final). User-ratified 2026-06-12: server side = Supabase (`agentdex.builders` project) as primary event store; client side = local SQLite for users' own agents' logs; dev = local Postgres container. RLS tenant-isolation + append-only + immutable-trigger PROVEN on Postgres 16 (test_eventsync.py).

# AgentDex Arena × BENE — Supabase Event-Sourcing Adaptor + Two-Tier Battle Observability

> Doctrine: **the local hash-chained log is always authoritative; Supabase is a durable read-mirror that can fail without ever stalling a battle.** Server side = authoritative Postgres (Supabase) for the fleet; client side = local SQLite for a user's own agents. BENE is the engram substrate under both.

## 1. Architecture

Two planes, one chain. The arena's existing append-only, blake2b16 **hash-chained `EventLog`** (`packages/agentdex_engine/.../modules/arena/events.py`) stays the byte-exact source of truth from which `recompute_ladder` rebuilds Glicko-2 ratings on a fresh checkout. Supabase Postgres becomes the authoritative *fleet* event store that fans those per-event lines into projections and serves multi-tenant reads under RLS. A user running their own agent keeps a **local SQLite** read-model of just their agents' battles — the same NDJSON chain, materialized — and can verify it without trusting the server. BENE underpins both: today `EngramStore`/`EventJournal` hard-bind a raw `sqlite3.Connection` (`engrams.py:110`, `events.py:34`); the new adaptor puts a `KernelBackend` behind them so the same append/search/lineage code runs on native SQLite (client, default, byte-identical) or Supabase Postgres (server, opt-in).

Nothing here claims realtime, vector search, or deterministic-replay tooling — **replay is a BENE *planned* feature** (`docs/design/CLAIMS-AUDIT.md:52`); this design only touches the append/search/lineage/checkpoint substrate that already ships.

## 2. The BENE backend adaptor

A **second** protocol package `bene/kernel/backend/` that *complements* the existing `bene/storage/` VFS surface (which already has `Storage`/`BlobStore` + `SqliteStorage` + `PostgresStorage` but covers only agents/files/state/tool_calls/checkpoints). The missing half is the **engram substrate**.

`KernelBackend` abstracts exactly the three couplings in `engrams.py`/`events.py`:

1. **`KernelConnection`** — `execute(sql, params) -> Cursor` / `executemany` / `commit` / `close`. `Cursor` exposes `fetchone`/`fetchall`/`lastrowid` (events.py:73) / `description` (core.py query()). The backend owns `?`→`$n` rewriting and `INSERT ... RETURNING` shimming, so `engrams.py`/`events.py` SQL is **untouched** on SQLite and minimally adapted on Postgres.
2. **`BlobBackend`** — `store(bytes)->(sha256,size)` / `retrieve` / `release` / `gc` / `stats`, preserving sha256 + zstd-level-3 + the `compressed` flag (`blobs.py:36,49-54`) on BYTEA or Supabase Storage.
3. **`FullTextIndex`** — the **only** piece with no portable SQL. `index(engram_id,title,body)` + `search(...)->[RankedRow]`. FTS5 `engram_fts MATCH ? ORDER BY bm25` (ascending = better) maps to `body_tsv @@ websearch_to_tsquery('english',$1) ORDER BY ts_rank_cd DESC` (descending = better) — and we **negate ts_rank_cd** so `RankedRow.score` keeps FTS5's *lower==better* meaning, or `Engram.score` (engrams.py:95) silently inverts across backends. The malformed-query path becomes a `supports_raise_on_malformed()` contract, not a leaked `except sqlite3.OperationalError` (engrams.py:299).

`EngramStore.__init__`/`EventJournal.__init__` take a `KernelBackend`; their public `append`/`search`/`log` signatures stay **verbatim** (engrams.py:121-135, :267-275; events.py:47-53). Validation (`kind in ENGRAM_KINDS`, `_validate_provenance`, `link_type in LINK_TYPES`) stays backend-agnostic.

- **`SqliteBackend`** (default, zero behavior change): wraps the existing thread-local `sqlite3.Connection` + `BlobStore`; `sqlite3.Connection` already satisfies `KernelConnection`; `supports_raw_query()=True`. This is the client path.
- **`SupabaseBackend`** (opt-in): raw **asyncpg 0.31** (already pinned under the `[temporal]` extra) behind a **sync facade pinning one pooled connection per logical `EngramStore`** — required to preserve the deferred-mirror read-your-writes + 'durable at caller's next commit' contract (`adapters.py:24-31`) that pool-reset would break. supabase-py is used **only** (optionally) for Supabase Storage blob offload, never SQL. Pooler in **transaction mode (6543)** with `statement_cache_size=0` (named prepared statements break under transaction pooling). Translations: `lineage()`'s `','.join('?'*len)` (engrams.py:328) → `WHERE src_id = ANY($1::text[])`; `INSERT OR IGNORE` → `ON CONFLICT ... DO NOTHING`; `cursor.lastrowid` → `INSERT ... RETURNING event_id`. `supports_raw_query()=False` — `core.py:637` `query()` is SQLite-only raw SELECT; the Postgres backend marks it `NotImplementedError` rather than faking dialect-neutrality.

## 3. Schema (append-only Postgres + projections)

See the DDL block. The engram tables mirror `schema_v2.py`; `created_at` is `timestamptz` but is **always read back through `to_char(...)` to the SQLite `%Y-%m-%dT%H:%M:%f` ISO-ms shape** so `Engram.created_at` string compares (engrams.py:407), `since` filters (events.py:90-92), and checkpoint watermarks (core.py:606) don't mis-order. FTS5 → a `body_tsv` generated column + GIN index (`'english'` ≠ FTS5 `'porter'`, so results differ on identical data — documented). The arena fleet log `arena_event_log` carries `tenant_id`, the per-battle `seq`, and the `prev` chain link, `unique(tenant_id, battle_id, seq)` for idempotent re-sync. Three projection tables (`arena_turn_state`, `arena_recent_turns`, `arena_ladder`) are maintained read-models, not views — so RLS scopes them and a turn read is a single-row PK lookup.

## 4. RLS (security-checklist-correct, append-only, consent-scoped)

See the RLS block. Clients are **not** Supabase-Auth users (the gateway authenticates agents with its own Ed25519 consent tokens), so `auth.uid() = user_id` is replaced by a **tenant predicate from a minted, Supabase-signed JWT whose tenant claim lives in `app_metadata`** (never `user_metadata`, which is end-user-editable). Hybrid posture:

- **Write** = the gateway with `service_role` (bypasses RLS), stamping `tenant_id` from the validated consent token + recording `consent_jti`. Application code is the write guard, not RLS.
- **Read** = enable + FORCE RLS; GRANT SELECT only; one `for select` policy per table keyed on the tenant claim (auth fn wrapped in a scalar subquery, evaluated once); `tenant_id` indexed.
- **Append-only** = no UPDATE/DELETE grant + no UPDATE/DELETE policy (denied by absence), **plus** a `BEFORE UPDATE/DELETE` trigger that RAISEs — because `service_role` bypasses RLS and would otherwise be able to mutate.
- **Alternate agent read path** = a private-schema `SECURITY DEFINER` RPC that validates the consent token itself, derives `tenant_id` in the body (never trusts a caller-passed one), with `EXECUTE` revoked from PUBLIC/anon/authenticated.
- Any future rollup VIEW MUST be `with (security_invoker = true)` or it re-exposes every tenant.

Run `supabase db advisors` after applying to catch exposed-table / SECURITY DEFINER findings.

## 5. Two-tier sync (server Postgres ↔ client SQLite)

Both planes are downstream of the same NDJSON hash chain. **Server**: gateway INSERTs each `EventLog` line into `arena_event_log` keyed `unique(tenant_id, battle_id, seq)` → idempotent (replayed line = no-op). The `prev` chain rides along, so even Postgres rows verify without trusting the DB. **Client**: `~/.adx/arena.sqlite` holds the same chain via the native `SqliteBackend` plus the small read-model tables, maintained by the same projector. The client never needs the server to play offline; it pulls (read-only, RLS-scoped) only missing `(battle_id, seq)` deltas. Conflict resolution is trivial-by-construction: append-only + seq-monotonic per battle → 'sync' is a **set-union on `(battle_id, seq)`** with the hash chain as the integrity check (no last-writer-wins, no merge). A client can **fork** a battle locally (copy the chain to seq=k into a fresh `battle_id`, continue, provenance back to origin) — fully offline.

## 6. Write path (per-turn appends OFF the turn-latency hot path)

The arena `EventLog.append` already takes an injected `sync: Callable[[dict],None]` (events.py:35) wrapped in try/except whose comment is the doctrine: *'sync failure NEVER blocks the append (the local log is the source of truth)'* (events.py:60-64). We do **not** make that sync a per-event round-trip — it **enqueues** onto a bounded in-process queue and returns; a background drainer batches `executemany`/COPY into `arena_event_log` and maintains projections write-behind.

One real latency bug fixed en route: `append` computes `seq` via `sum(1 for _ in self.iter_events())` (events.py:51) and `_last_digest` re-reads the whole file (events.py:39-47) — both **O(file) per append**, which is the actual per-turn cost, not Supabase. P1 keeps an in-memory `(seq, last_digest)` watermark → O(1) append, writing identical bytes (golden-tested). BENE-side mirror appends already batch via `deferred=True` (engrams.py:182-191, `DEFER_BUFFER_CAP=64`) and ride the caller's transaction; `SupabaseBackend` pins one pooled conn per `EngramStore` so the batched flush lands in one transaction.

Net: per-turn cost = one local append; Supabase reached only in batches on a background thread; a Supabase outage degrades to 'projections lag' — zero turn-latency impact, zero data loss.

## 7. Phased plan

| Phase | Item | Effort | Gated on |
|---|---|---|---|
| **P1** | Read-only event emit: O(1) append (in-memory seq+digest watermark) + route `sync` to a write-behind queue. **Determinism-sensitive → FIRST**; byte-identical lines, `verify_chain`/`recompute_ladder` green. | M | nothing — uses the `EventLog.sync` seam that already exists; golden byte-equality test |
| **P2** | BENE backend adaptor (protocols + Sqlite/Supabase backends, constructors repointed) + Supabase schema/RLS applied; gateway writes via service_role + tenant_id. | L | P1 + **real Supabase credentials** + asyncpg (`[temporal]`) |
| **P3** | Projections → `arena_turn_state` / `arena_recent_turns` / `arena_ladder`; `foe_hp_pct` derived at the protocol-parse sanitize boundary. | M | P2 |
| **P4** | Client SQLite pull + local fork (#6): native SqliteBackend materializes `~/.adx/arena.sqlite`; RLS-scoped delta pull; offline fork-from-seq-k. | M | P3 + minted-JWT or SECURITY DEFINER read path |

## 8. Guarantees

- **Determinism preserved** — hash-chained local log is SoT; `recompute_ladder` replays byte-identically; P1 writes identical bytes; sync failure never blocks an append.
- **RLS-correct & append-only** — FORCE RLS; SELECT-only / INSERT-only grants; one tenant `for select` policy; immutability trigger defeats even `service_role`; `app_metadata` only; auth fn in a subquery; `tenant_id` indexed.
- **Consent-scoped multi-tenancy** without Supabase Auth — gateway is the write guard; agents read via minted JWT or private SECURITY DEFINER RPC.
- **No BENE planned-feature claims** — no replay API (PLANNED, CLAIMS-AUDIT:52); `kernel:` config landed additively defaulting to sqlite (PLANNED, :53); no scheduler (PLANNED, :26); no realtime/vector — FTS stays lexical; `'english'` ≠ `'porter'` documented.
- **Latency-safe** — per-turn = one local append; Supabase batched write-behind; outage = projections lag only.
- **Nano-fit** — transaction-pooler (6543, `statement_cache_size=0`); bounded queue caps RAM; one pinned conn per `EngramStore`.
- **Client data ownership** — local SQLite holds the verifiable chain offline; sync is an idempotent set-union.

## 9. Credential gate

The op item **`Supabase  agentdex database`** (`linqpieb5d4xuipvqfbrouneby`, vault `openclaw`) is the wiring target and is **currently empty/inaccessible** from this env (stale op token). To go live it needs: **project ref/URL**; **transaction-mode pooler DSN** (6543, `postgres.<ref>`); **service_role key** (gateway-only secret); **anon/publishable key** (client reads); **JWT signing secret** (to mint per-consent-token JWTs with `tenant_id` in `app_metadata`); and the **consent-token ↔ tenant_id mapping convention**. Until populated, the whole design is buildable/testable against a local `supabase start` (same DDL/RLS); the live op item is the only blocker for P2's 'write to the real project' step.

---

## Status updates

- 2026-06-12 — **P4 SHIPPED** (arena/q2 PR): `/my/events` tenant-scoped chain pull + `agentdex_arena.local_log` materializing `~/.adx/arena.sqlite` (idempotent set-union on (battle_id, seq); offline `battles()` + `recent_story()`). **#6 fork SHIPPED**: sandbox-only `POST /battle/{id}/fork` — same seed/teams/fresh-seeded opponent policy, recorded visitor choices replayed through the live step protocol to turn N; full-replay forks reproduce the original winner (determinism proof in test); rated + foreign forks 403; public `/replay` view filtered (seed/teams/choices/tenant stay server-side).

## Appendix — Rejected: browser-WASM performance modules (user-ratified 2026-06-12)

Proposal considered: compile "performance modules" to WASM and run them in the user's
browser for smoothness + security. **Rejected, three grounds:** (1) wrong bottleneck —
per-turn latency is dominated by the agent's LLM call (s) ≫ HTTP RTT (10s of ms) ≫ one
sim step (<1ms; full battles measure 0.1–0.7s wall); the dogfood complaint was information
visibility, not speed. (2) wrong security direction — rated-lane outcomes must stay
server-authoritative (server-secret seeds, hash chain, resim audit); client-side simulation
hands the reward function to the adversary, the exact Clawvard-class trap this arena is
built against. (3) nothing to compile — the Showdown sim is TypeScript/JS; a browser runs
it natively, WASM adds nothing over a JS bundle.

**Two kernels extracted and kept:** (a) local advisory sim for agents = P4's local sidecar
(same pinned version, node, advisory-only; rated results remain server-side) — delivers the
zero-RTT planning win safely; (b) WASM sandboxing belongs server-side IF a future
"submit-your-bot-script" lane ever ships (post-phase-10 product decision, not current work).
