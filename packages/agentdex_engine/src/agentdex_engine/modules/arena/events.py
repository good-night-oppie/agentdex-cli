"""Append-only, hash-chained arena event log (IDEAL §Arena A8).

Every battle appends one canonical-JSON line carrying the blake2b16 of the
previous line — ratings recompute byte-identically from the log on a fresh
checkout, and an outsider can verify the chain without trusting the server.
`sync` is an injected per-event callable (the deploy phase wires Supabase);
sync failure NEVER blocks the append (the local log is the source of truth).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from agentdex_engine.modules.arena.ladder import Ladder, RatingEvent

log = logging.getLogger(__name__)

GENESIS = "0" * 32


def _digest(line: str) -> str:
    return hashlib.blake2b(line.encode(), digest_size=16).hexdigest()


class ChainError(ValueError):
    """Hash chain broken — the log was edited or truncated mid-file."""


class EventLog:
    def __init__(self, path: str | Path, *, sync: Callable[[dict], None] | None = None) -> None:
        self.path = Path(path)
        self._sync = sync

    def _last_digest(self) -> str:
        if not self.path.is_file():
            return GENESIS
        last = None
        with self.path.open() as fh:
            for raw in fh:
                if raw.strip():
                    last = raw.rstrip("\n")
        return _digest(last) if last else GENESIS

    def append(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "seq": sum(1 for _ in self.iter_events()),
            "type": type_,
            "prev": self._last_digest(),
            "payload": payload,
        }
        line = json.dumps(event, sort_keys=True, separators=(",", ":"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(line + "\n")
        if self._sync is not None:
            try:
                self._sync(event)
            except Exception:
                log.exception("event sync failed (local log remains authoritative)")
        return event

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if not self.path.is_file():
            return
        with self.path.open() as fh:
            for raw in fh:
                if raw.strip():
                    yield json.loads(raw)

    def verify_chain(self) -> int:
        """Returns event count; raises ChainError on any break (A8)."""
        prev = GENESIS
        count = 0
        if not self.path.is_file():
            return 0
        with self.path.open() as fh:
            for raw in fh:
                raw = raw.rstrip("\n")
                if not raw:
                    continue
                event = json.loads(raw)
                if event.get("prev") != prev:
                    raise ChainError(f"chain break at seq={event.get('seq')}")
                prev = _digest(raw)
                count += 1
        return count


def recompute_ladder(
    log_path: str | Path,
    *,
    frozen: set[str] | None = None,
) -> Ladder:
    """Replay the event log into a fresh Ladder — byte-identical recompute.

    Events of type 'register' add entrants; 'period' events carry a list of
    rating events applied as ONE Glicko-2 rating period.
    """
    elog = EventLog(log_path)
    elog.verify_chain()
    ladder = Ladder()
    for event in elog.iter_events():
        payload = event["payload"]
        if event["type"] == "register":
            ladder.register(payload["name"], frozen=bool(payload.get("frozen", False)))
        elif event["type"] == "period":
            ladder.rate_period([RatingEvent(**ev) for ev in payload["events"]])
    return ladder
