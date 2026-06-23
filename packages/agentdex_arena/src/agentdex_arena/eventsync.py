"""Write-behind Postgres mirror for the arena's hash-chained EventLog.

Doctrine (BENE-Supabase design note, 2026-06-12): the local NDJSON chain is the
ONLY synchronous write and stays the source of truth; Postgres (dev: local
container; prod: Supabase pooler) is a durable downstream mirror feeding
projections + multi-tenant reads. The injected `EventLog.sync` callable must
never add network RTT to a battle turn, so `WriteBehindSync.__call__` only
enqueues onto a bounded in-process queue and returns; a daemon thread drains
batches into `arena_event_log` with ON CONFLICT DO NOTHING (idempotent —
re-syncing a replayed chain is a no-op). A Postgres outage degrades to
"mirror lags"; the local log replays the gap on the next full resync.

Connection notes (prod): use the Supabase TRANSACTION-mode pooler (port 6543)
DSN and statement_cache_size=0 — named prepared statements break under
transaction pooling. Dev: any plain Postgres DSN works.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Any

log = logging.getLogger(__name__)

# One source of truth for the mirror schema; mirrored verbatim in
# migrations/0001_arena_event_log.sql for the prod (Supabase) apply.
ARENA_EVENT_LOG_DDL = """
create table if not exists arena_event_log (
  id          bigint generated always as identity primary key,
  tenant_id   text not null,
  battle_id   text not null,
  seq         bigint not null,
  event_type  text not null,
  prev_digest text not null,
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  unique (tenant_id, battle_id, seq)
);
alter table arena_event_log enable row level security;
alter table arena_event_log force row level security;

-- Read scoping: each tenant (arena consent token) sees only its own rows.
-- The gateway authenticates agents with its OWN Ed25519 consent tokens (not
-- Supabase Auth), so the tenant predicate is a per-connection GUC the reader
-- path sets AFTER validating the token (RLS-POC-verified on Postgres 16).
drop policy if exists arena_event_tenant_select on arena_event_log;
create policy arena_event_tenant_select on arena_event_log for select
  using (tenant_id = current_setting('app.tenant_id', true));
drop policy if exists arena_event_tenant_insert on arena_event_log;
create policy arena_event_tenant_insert on arena_event_log for insert
  with check (tenant_id = current_setting('app.tenant_id', true));
-- NO update/delete policy => append-only by absence of policy.

-- Belt-and-suspenders: service_role/superuser BYPASS RLS, so a trigger makes
-- the log physically immutable for EVERY role including the gateway's own.
create or replace function arena_event_log_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'arena_event_log is append-only (% denied)', tg_op;
end; $$;
drop trigger if exists arena_event_no_mutate on arena_event_log;
create trigger arena_event_no_mutate
  before update or delete on arena_event_log
  for each row execute function arena_event_log_immutable();
"""

_INSERT = """
insert into arena_event_log (tenant_id, battle_id, seq, event_type, prev_digest, payload)
values ($1, $2, $3, $4, $5, $6::jsonb)
on conflict (tenant_id, battle_id, seq) do nothing
"""

HOUSE_TENANT = "_house"  # rating-chain events (register/period) have no visitor tenant
LADDER_BATTLE = "_ladder"

# GA-ARENA-MODES: PvP event types logged in the battle_begin payload.
# mode="pvp" is stored in payload JSONB (no DDL column change needed).
PVP_QUEUE_ENTER = "pvp_queue_enter"  # owner entered the matchmaking queue
PVP_MATCH = "pvp_match"  # two owners paired; battle_id + roles logged


def _event_row(event: dict[str, Any]) -> tuple[str, str, int, str, str, str]:
    payload = event.get("payload") or {}
    tenant = str(payload.get("tenant_id") or HOUSE_TENANT)
    battle = str(payload.get("battle_id") or LADDER_BATTLE)
    return (
        tenant,
        battle,
        int(event["seq"]),
        str(event["type"]),
        str(event.get("prev", "")),
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )


class WriteBehindSync:
    """`EventLog.sync`-compatible callable: enqueue now, mirror later.

    `__call__` never blocks the turn path: on a full queue the event is DROPPED
    from the MIRROR (counted + logged) — the local chain still has it, and a
    later full resync re-mirrors idempotently.
    """

    def __init__(
        self,
        dsn: str,
        *,
        maxsize: int = 10_000,
        batch_max: int = 200,
        flush_interval_s: float = 0.5,
        apply_ddl: bool = False,
        statement_cache_size: int = 0,
    ) -> None:
        self._dsn = dsn
        self._batch_max = batch_max
        self._flush_interval_s = flush_interval_s
        self._apply_ddl = apply_ddl
        self._statement_cache_size = statement_cache_size
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=maxsize)
        self.dropped = 0
        self.mirrored = 0
        self.last_error: str | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="arena-event-mirror", daemon=True)
        self._thread.start()

    # ---- hot path (the EventLog sync seam) ----

    def __call__(self, event: dict[str, Any]) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            if self.dropped % 1000 == 1:
                log.warning(
                    "event mirror queue full — dropped %d (local log authoritative)", self.dropped
                )

    # ---- background drainer ----

    def _run(self) -> None:
        asyncio.run(self._drain_forever())

    async def _connect(self):
        import asyncpg

        conn = await asyncpg.connect(self._dsn, statement_cache_size=self._statement_cache_size)
        if self._apply_ddl:
            await conn.execute(ARENA_EVENT_LOG_DDL)
        return conn

    async def _drain_forever(self) -> None:
        conn = None
        pending_retry: list[dict[str, Any]] = []
        while not self._closed:
            batch: list[dict[str, Any]] = []
            if pending_retry:
                batch.extend(pending_retry)
                pending_retry.clear()
            else:
                try:
                    first = await asyncio.to_thread(self._q.get)
                except Exception:
                    return
                if first is None:
                    break
                batch.append(first)
            while len(batch) < self._batch_max:
                try:
                    nxt = self._q.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    try:
                        self._q.put_nowait(None)
                    except queue.Full:
                        pass
                    break
                batch.append(nxt)
            rows = [_event_row(e) for e in batch]
            success = False
            for attempt in (1, 2, 3):
                try:
                    if conn is None or conn.is_closed():
                        conn = await self._connect()
                    await conn.executemany(_INSERT, rows)
                    self.mirrored += len(rows)
                    self.last_error = None
                    success = True
                    break
                except Exception as e:  # noqa: BLE001 — mirror must never crash the app
                    self.last_error = f"{type(e).__name__}: {e}"
                    log.warning(
                        "event mirror flush failed (attempt %d/3): %s", attempt, self.last_error
                    )
                    conn = None
                    await asyncio.sleep(min(2.0 * attempt, self._flush_interval_s * 4))
            if not success:
                pending_retry.extend(batch)
                if self._closed:
                    log.error(
                        "event mirror failed all flush attempts during shutdown; dropping %d events",
                        len(pending_retry),
                    )
                    break
            await asyncio.sleep(self._flush_interval_s)
        if conn is not None and not conn.is_closed():
            await conn.close()

    def close(self, *, timeout_s: float = 10.0) -> None:
        """Flush the queue and stop the drainer (tests / graceful shutdown)."""
        self._closed = True
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=timeout_s)
