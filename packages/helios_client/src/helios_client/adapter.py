"""helios_client SQLite-backed CheckpointStore stub.

Per ADR-0009 §D2 + ROADMAP §A1: helios.go ships only CGO bindings (no gRPC server).
MVP M2-M5 needs zero helios integration. The CheckpointStore Protocol is
implemented over SQLite so engine + plugin code can store/restore checkpoints
through a stable interface; M6 benchmark replaces with FFI-via-libhelios.a or
added-gRPC-layer depending on RTT measurements.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol


class CheckpointStore(Protocol):
    """Minimal CheckpointStore Protocol — checkpoint, restore, list, delete."""

    def checkpoint(self, key: str, payload: dict[str, Any]) -> str:
        """Persist payload under key. Returns checkpoint ID (sha or rowid)."""
        ...

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Read payload by checkpoint_id."""
        ...

    def list_checkpoints(self, prefix: str | None = None) -> list[str]:
        """List checkpoint IDs, optionally filtered by key prefix."""
        ...

    def delete(self, checkpoint_id: str) -> bool:
        """Delete checkpoint by ID. Returns True if removed."""
        ...


class SqliteCheckpointStore:
    """SQLite-backed CheckpointStore — M2 stub adapter for helios_client.

    Schema: one table `checkpoints (id TEXT PK, key TEXT, payload JSON, created_at REAL)`.
    Threading: each call opens its own connection (SQLite WAL-friendly).
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_key ON checkpoints(key)")

    def checkpoint(self, key: str, payload: dict[str, Any]) -> str:
        cid = f"{key}@{int(time.time_ns())}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO checkpoints (id, key, payload, created_at) VALUES (?, ?, ?, ?)",
                (cid, key, json.dumps(payload), time.time()),
            )
        return cid

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload FROM checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"checkpoint not found: {checkpoint_id}")
        return json.loads(row[0])

    def list_checkpoints(self, prefix: str | None = None) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            if prefix is None:
                rows = conn.execute("SELECT id FROM checkpoints ORDER BY created_at").fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM checkpoints WHERE key LIKE ? ORDER BY created_at",
                    (f"{prefix}%",),
                ).fetchall()
        return [r[0] for r in rows]

    def delete(self, checkpoint_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
            return cur.rowcount > 0
