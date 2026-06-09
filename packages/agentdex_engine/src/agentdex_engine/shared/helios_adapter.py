"""Checkpoint store — SQLite blob fallback for MVP; helios CAS later.

Per ADR-0005, helios Vector A (Merkle CAS) is the production target for
checkpoint storage but is gated until ionq simplify-v1 unblocks. For PHASE-2
MVP, we use a content-addressed SQLite blob store with the same
`CheckpointStore` Protocol — swap-in later requires no client change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, cast

import aiosqlite


class CheckpointStore(Protocol):
    """Content-addressed blob storage for battle checkpoint state."""

    async def put(self, state: dict[str, Any]) -> str:
        """Returns the content hash. Idempotent for identical state."""
        ...

    async def get(self, state_hash: str) -> dict[str, Any]:
        """Raises KeyError if hash unknown."""
        ...

    async def exists(self, state_hash: str) -> bool: ...


DEFAULT_DB_PATH = Path.home() / ".cache" / "agentdex" / "checkpoints.db"


class SQLiteCheckpointStore:
    """SHA-256-keyed blob store. Single-writer assumption."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _init(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    hash TEXT PRIMARY KEY,
                    payload BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()
        self._initialized = True

    @staticmethod
    def _hash(state: dict[str, Any]) -> str:
        payload = json.dumps(state, sort_keys=True, default=str).encode()
        return hashlib.sha256(payload).hexdigest()[:16]

    async def put(self, state: dict[str, Any]) -> str:
        await self._init()
        state_hash = self._hash(state)
        payload = json.dumps(state, sort_keys=True, default=str).encode()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO checkpoints (hash, payload) VALUES (?, ?)",
                (state_hash, payload),
            )
            await db.commit()
        return state_hash

    async def get(self, state_hash: str) -> dict[str, Any]:
        await self._init()
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute("SELECT payload FROM checkpoints WHERE hash = ?", (state_hash,)) as cursor,
        ):
            row = await cursor.fetchone()
        if row is None:
            raise KeyError(f"unknown checkpoint hash: {state_hash}")
        return cast(dict[str, Any], json.loads(row[0]))

    async def exists(self, state_hash: str) -> bool:
        await self._init()
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute("SELECT 1 FROM checkpoints WHERE hash = ? LIMIT 1", (state_hash,)) as cursor,
        ):
            return (await cursor.fetchone()) is not None
