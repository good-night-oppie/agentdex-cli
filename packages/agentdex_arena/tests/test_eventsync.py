"""Write-behind Postgres mirror (BENE-Supabase design P1/P2-dev).

The Postgres tests run against a local dev container (ARENA_TEST_PG_DSN,
default the adx-pg container on :55432) and skip cleanly when unreachable —
same posture as the sidecar gate. Prod (Supabase) differs only by DSN.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from agentdex_arena.eventsync import (
    ARENA_EVENT_LOG_DDL,
    WriteBehindSync,
    _event_row,
)

PG_DSN = os.environ.get("ARENA_TEST_PG_DSN", "postgresql://postgres:arena@127.0.0.1:55432/arena")


def _pg_available() -> str | None:
    try:
        import asyncio

        import asyncpg

        async def ping():
            conn = await asyncpg.connect(PG_DSN, timeout=3)
            await conn.close()

        asyncio.run(ping())
        return None
    except Exception as e:  # noqa: BLE001
        return f"postgres unreachable: {type(e).__name__}"


_PG_SKIP = _pg_available()


def test_migration_file_matches_ddl_constant():
    """The prod migration is GENERATED from the Python constant — they must not drift."""
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1] / "migrations" / "0001_arena_event_log.sql"
    ).read_text()
    assert ARENA_EVENT_LOG_DDL in sql


def test_event_row_tenant_mapping():
    row = _event_row(
        {
            "seq": 3,
            "type": "battle",
            "prev": "ab",
            "payload": {"tenant_id": "tokX", "battle_id": "b1", "turn": 2},
        }
    )
    assert row[0] == "tokX" and row[1] == "b1" and row[2] == 3 and row[3] == "battle"
    # rating-chain events without tenant land under the house tenant
    row2 = _event_row({"seq": 0, "type": "register", "prev": "0" * 32, "payload": {"name": "X"}})
    assert row2[0] == "_house" and row2[1] == "_ladder"


@pytest.mark.skipif(_PG_SKIP is not None, reason=str(_PG_SKIP))
def test_write_behind_mirrors_idempotently_and_rls_scopes(tmp_path):
    """End-to-end vs real Postgres: events flow through the EventLog sync seam to
    arena_event_log; re-sync is a no-op; RLS scopes reads per consent token; the
    immutable trigger refuses UPDATE/DELETE for every role."""
    import asyncio

    import asyncpg
    from agentdex_engine.modules.arena import EventLog

    marker = uuid.uuid4().hex[:10]
    tenant_a, tenant_b = f"tokA-{marker}", f"tokB-{marker}"

    sync = WriteBehindSync(PG_DSN, apply_ddl=True, flush_interval_s=0.05)
    elog = EventLog(tmp_path / "events.jsonl", sync=sync)
    elog.append(
        "battle_begin", {"tenant_id": tenant_a, "battle_id": f"b-{marker}", "lane": "sandbox"}
    )
    elog.append(
        "battle", {"tenant_id": tenant_a, "battle_id": f"b-{marker}", "turn": 1, "choice": "move 1"}
    )
    elog.append(
        "battle", {"tenant_id": tenant_b, "battle_id": f"c-{marker}", "turn": 1, "choice": "move 2"}
    )
    # duplicate of seq 1 (a chain replay) must be a no-op via ON CONFLICT
    sync(
        {
            "seq": 1,
            "type": "battle",
            "prev": "x",
            "payload": {
                "tenant_id": tenant_a,
                "battle_id": f"b-{marker}",
                "turn": 1,
                "choice": "move 1",
            },
        }
    )
    deadline = time.time() + 15
    while time.time() < deadline and sync.mirrored < 4:
        time.sleep(0.1)
    sync.close()
    assert sync.mirrored >= 4 and sync.last_error is None, sync.last_error

    async def checks():
        admin = await asyncpg.connect(PG_DSN)
        n_a = await admin.fetchval(
            "select count(*) from arena_event_log where tenant_id=$1", tenant_a
        )
        assert n_a == 2, f"idempotent mirror expected 2 rows for A, got {n_a}"
        # immutable trigger refuses even superuser mutation
        try:
            await admin.execute(
                "update arena_event_log set event_type='x' where tenant_id=$1", tenant_a
            )
            raise AssertionError("UPDATE must be refused by the immutable trigger")
        except asyncpg.exceptions.RaiseError:
            pass
        # RLS scoping under a non-bypass role (create if missing)
        await admin.execute("""
            do $$ begin
              if not exists (select 1 from pg_roles where rolname='arena_reader') then
                create role arena_reader login password 'r';
              end if;
            end $$;
            grant select on arena_event_log to arena_reader;
        """)
        await admin.close()
        reader = await asyncpg.connect(
            PG_DSN.replace("postgres:arena", "arena_reader:r"), statement_cache_size=0
        )
        await reader.execute("select set_config('app.tenant_id', $1, false)", tenant_a)
        sees_a = await reader.fetchval(
            "select count(*) from arena_event_log where tenant_id like $1", f"%{marker}"
        )
        await reader.execute("select set_config('app.tenant_id', $1, false)", tenant_b)
        sees_b = await reader.fetchval(
            "select count(*) from arena_event_log where tenant_id like $1", f"%{marker}"
        )
        await reader.close()
        assert sees_a == 2 and sees_b == 1, (
            f"RLS leak: A sees {sees_a} (want 2), B sees {sees_b} (want 1)"
        )

    asyncio.run(checks())
    print(
        f"\nEVENT_MIRROR: 4 rows mirrored, replay idempotent, RLS isolates {tenant_a[:8]}/{tenant_b[:8]}, immutable trigger holds"
    )


def test_write_behind_sync_retry_and_preserve():
    from unittest.mock import AsyncMock

    sync = WriteBehindSync("postgresql://dummy", flush_interval_s=0.01)

    # Mock _connect to fail initially
    sync._connect = AsyncMock(side_effect=Exception("Database down"))

    # Enqueue a dummy event
    sync({"seq": 1, "type": "dummy", "prev": "a", "payload": {}})

    # Wait for the attempts to fail (attempts sleep for 2s, 4s, etc., wait, let's check:
    # min(2.0 * attempt, self._flush_interval_s * 4) -> min(2.0, 0.04) -> 0.04s!
    # So 3 attempts will sleep 0.02s, 0.04s, 0.04s, which is very fast in this test!
    # Let's wait a bit to ensure all 3 attempts have failed.
    time.sleep(0.3)

    assert sync._connect.call_count >= 3
    assert sync.last_error is not None and "Database down" in sync.last_error
    assert sync.mirrored == 0

    # Now make it succeed
    mock_conn = AsyncMock()
    mock_conn.is_closed = lambda: False
    sync._connect = AsyncMock(return_value=mock_conn)

    deadline = time.time() + 5
    while time.time() < deadline and sync.mirrored == 0:
        time.sleep(0.05)

    sync.close()

    assert sync.mirrored == 1
    assert mock_conn.executemany.call_count >= 1


def test_write_behind_sync_close_deadlock_when_queue_full():
    """Test that WriteBehindSync.close() does not deadlock when the queue is full and database is unreachable."""
    from unittest.mock import AsyncMock

    # Create a sync instance with a tiny queue maxsize
    sync = WriteBehindSync("postgresql://dummy", maxsize=3, flush_interval_s=0.1)

    # Mock _connect to fail so the worker is stuck retrying/failing
    sync._connect = AsyncMock(side_effect=Exception("Database down"))

    # Fill the queue (size is 3)
    sync({"seq": 1, "type": "dummy", "prev": "a", "payload": {}})
    sync({"seq": 2, "type": "dummy", "prev": "a", "payload": {}})
    sync({"seq": 3, "type": "dummy", "prev": "a", "payload": {}})

    # Wait a moment to ensure worker starts trying
    time.sleep(0.15)

    # Close the sync instance with a timeout, this should return without deadlocking
    start = time.time()
    sync.close(timeout_s=2.0)
    duration = time.time() - start

    assert duration < 2.0, f"close() deadlocked for {duration:.2f} seconds"
    assert sync._closed is True
