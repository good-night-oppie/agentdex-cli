"""helios_client — SQLite-backed stub at M2 per ADR-0009 §D2.

The full FFI vs gRPC decision is deferred to M6 benchmark per ADR-0009. This module
ships a `CheckpointStore` Protocol implementation against SQLite so the M2-M5 MVP
chain can persist checkpoints without requiring helios.go integration.
"""

from helios_client.adapter import CheckpointStore, SqliteCheckpointStore

__all__ = ["CheckpointStore", "SqliteCheckpointStore"]
