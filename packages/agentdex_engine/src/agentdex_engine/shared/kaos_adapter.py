"""KAOS-backed CheckpointStore adapter + Expedition lineage helper.

Per ADR-0009 §D1 + ADR-0008 §Amendment-2026-06-07 (bene→KAOS substrate pivot),
the Hermes-exclusive memory provider is backed by KAOS db.checkpoint /
db.restore and blob storage. This module wraps the KAOS Python API behind the
CheckpointStore Protocol shared with helios_client.adapter (M6 swap target),
AND exposes :func:`log_expedition_lineage` for M5 phase-7 Expedition lineage
persistence (acceptance criterion 10 of phase-7).
"""

from __future__ import annotations

import json
from pathlib import Path
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


def log_expedition_lineage(
    db_path: str | Path,
    expedition_id: str,
    evolution_card_dict: dict[str, Any],
    *,
    parent_lineage_root: str | None = None,
) -> str | None:
    """Persist an Expedition lineage entry in KAOS.

    Spawns a KAOS agent named ``expedition-<id>``, stores the EvolutionCard
    payload as a state blob keyed ``evolution_card``, then snapshots a final
    checkpoint labelled ``expedition-final``. Returns the spawned agent_id
    (used as the lineage anchor) — or ``None`` if KAOS is unavailable, so
    the Expedition still completes when KAOS is offline.

    Per ADR-0009 §M5: KAOS stores lineage durably so M10 can walk
    parent-child via accepted seeds.
    """
    try:
        from kaos import Kaos
    except ImportError:
        return None
    try:
        kaos = Kaos(str(db_path))
        agent_id = kaos.spawn(
            name=f"expedition-{expedition_id}",
            parent_id=parent_lineage_root,
        )
        kaos.set_state(
            agent_id,
            "evolution_card_json",
            json.dumps(evolution_card_dict, ensure_ascii=False, default=str),
        )
        kaos.set_state(agent_id, "expedition_id", expedition_id)
        kaos.checkpoint(agent_id, label="expedition-final")
        return agent_id
    except Exception:  # pragma: no cover — KAOS sqlite hiccups shouldn't kill Expedition
        return None


def list_expedition_lineage(
    db_path: str | Path, *, prefix: str = "expedition-"
) -> list[dict[str, Any]]:
    """Return KAOS agents whose name begins with ``prefix``."""
    try:
        from kaos import Kaos
    except ImportError:
        return []
    try:
        kaos = Kaos(str(db_path))
        agents = kaos.list_agents()
        return [a for a in agents if (a.get("name") or "").startswith(prefix)]
    except Exception:  # pragma: no cover
        return []
