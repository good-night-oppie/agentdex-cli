"""KAOS-backed CheckpointStore adapter — Hermes-exclusive memory provider.

Per ADR-0009 §D1 + ADR-0008 §Amendment-2026-06-07 (bene→KAOS substrate pivot),
the Hermes-exclusive memory provider is backed by KAOS db.checkpoint / db.restore
and blob storage. This module wraps the KAOS Python API behind the
CheckpointStore Protocol shared with helios_client.adapter (M6 swap target).

Note: this is a M2 STUB. The full KAOS substrate integration (MemoryStore +
SkillStore + SharedLog + experiments.log) lands at M5 phase-7 when the
Expedition lineage is first persisted. For M2 phase-4, only the
CheckpointStore Protocol surface is required to satisfy plugin discovery and
ensure import-time integrity.
"""

from __future__ import annotations

from typing import Any

from helios_client.adapter import CheckpointStore


class KaosCheckpointStore:
    """KAOS-backed CheckpointStore — stub at M2; wires to Kaos(db) at M5+.

    Implements the same CheckpointStore Protocol as SqliteCheckpointStore so
    callers can swap implementations without code changes. The actual
    Kaos(db).checkpoint() / .restore() integration ships at M5 phase-7.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._inner: CheckpointStore | None = None

    def _ensure_kaos(self) -> CheckpointStore:
        """Lazy-init the KAOS-backed inner store. M2 falls back to SQLite stub."""
        if self._inner is not None:
            return self._inner
        try:
            from kaos import Kaos  # noqa: F401  -- ensures kaos importable

            # M5 phase-7 wires the actual Kaos(db).checkpoint API here.
            # For M2, fall back to SqliteCheckpointStore so the protocol holds.
            from helios_client.adapter import SqliteCheckpointStore

            self._inner = SqliteCheckpointStore(self.db_path)
            return self._inner
        except ImportError:
            from helios_client.adapter import SqliteCheckpointStore

            self._inner = SqliteCheckpointStore(self.db_path)
            return self._inner

    def checkpoint(self, key: str, payload: dict[str, Any]) -> str:
        return self._ensure_kaos().checkpoint(key, payload)

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        return self._ensure_kaos().restore(checkpoint_id)

    def list_checkpoints(self, prefix: str | None = None) -> list[str]:
        return self._ensure_kaos().list_checkpoints(prefix)

    def delete(self, checkpoint_id: str) -> bool:
        return self._ensure_kaos().delete(checkpoint_id)
