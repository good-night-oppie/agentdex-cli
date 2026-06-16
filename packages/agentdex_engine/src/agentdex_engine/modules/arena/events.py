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
import os
import tempfile
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
        # (seq, last_digest, file_size) watermark — makes append O(1) instead of two
        # full-file rescans per event (the measured per-turn cost once battles append
        # per-turn events). Lazily initialized from the file once; appends maintain it.
        # A stat() size check per append detects a second writer (the pre-watermark
        # implementation re-read the file every append, so it tolerated one) and falls
        # back to a reload. Byte-identical lines to the pre-watermark implementation.
        self._watermark: tuple[int, str, int] | None = None

    def _load_watermark(self) -> tuple[int, str, int]:
        if not self.path.is_file():
            return (0, GENESIS, 0)
        count = 0
        last = None
        size = self.path.stat().st_size
        with self.path.open() as fh:
            for raw in fh:
                if raw.strip():
                    last = raw.rstrip("\n")
                    count += 1
        return (count, _digest(last) if last else GENESIS, size)

    def _current_watermark(self) -> tuple[int, str, int]:
        if self._watermark is not None:
            actual = self.path.stat().st_size if self.path.is_file() else 0
            if actual == self._watermark[2]:
                return self._watermark
        self._watermark = self._load_watermark()
        return self._watermark

    def _last_digest(self) -> str:
        return self._current_watermark()[1]

    def append(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        lock_path = self.path.parent / f"{self.path.name}.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import fcntl

        with open(lock_path, "w") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            seq, prev, size = self._current_watermark()
            event = {
                "seq": seq,
                "type": type_,
                "prev": prev,
                "payload": payload,
            }
            line = json.dumps(event, sort_keys=True, separators=(",", ":"))
            data = line + "\n"
            with self.path.open("a") as fh:
                fh.write(data)
            self._watermark = (seq + 1, _digest(line), size + len(data.encode()))

        if self._sync is not None:
            try:
                self._sync(event)
            except Exception:
                log.exception("event sync failed (local log remains authoritative)")
        return event

    def append_many(self, items: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """Append a group of events as one local-log transaction.

        Arena receipts can span several chain rows (battle_end + badge +
        quarantine + rating period). A partial group would let the durable log
        claim a different result than the public receipt/replay surface. Build
        the whole next file under the log lock and atomically replace the log so
        either every row lands with a valid hash chain or none do.
        """
        if not items:
            return []

        lock_path = self.path.parent / f"{self.path.name}.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import fcntl

        events: list[dict[str, Any]] = []
        tmp_name: str | None = None
        with open(lock_path, "w") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            seq, prev, size = self._current_watermark()
            lines: list[str] = []
            for offset, (type_, payload) in enumerate(items):
                event = {
                    "seq": seq + offset,
                    "type": type_,
                    "prev": prev,
                    "payload": payload,
                }
                line = json.dumps(event, sort_keys=True, separators=(",", ":"))
                events.append(event)
                lines.append(line + "\n")
                prev = _digest(line)

            old = self.path.read_bytes() if self.path.is_file() else b""
            data = "".join(lines).encode()
            try:
                with tempfile.NamedTemporaryFile(
                    "wb", delete=False, dir=self.path.parent, prefix=f".{self.path.name}."
                ) as tmp:
                    tmp_name = tmp.name
                    tmp.write(old)
                    tmp.write(data)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_name, self.path)
                tmp_name = None
                self._watermark = (seq + len(events), prev, size + len(data))
            finally:
                if tmp_name is not None:
                    try:
                        os.unlink(tmp_name)
                    except FileNotFoundError:
                        pass

        if self._sync is not None:
            for event in events:
                try:
                    self._sync(event)
                except Exception:
                    log.exception("event sync failed (local log remains authoritative)")
        return events

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if not self.path.is_file():
            return
        with self.path.open() as fh:
            for raw in fh:
                if raw.strip():
                    yield json.loads(raw)

    def verify_chain(self, expected_digest: str | None = None) -> int:
        """Returns event count; raises ChainError on any break (A8)."""
        prev = GENESIS
        count = 0
        if not self.path.is_file():
            if expected_digest is not None and expected_digest != GENESIS:
                raise ChainError("expected digest mismatch: empty log")
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
        if expected_digest is not None and prev != expected_digest:
            raise ChainError(
                f"expected digest mismatch at tail: got {prev}, expected {expected_digest}"
            )
        return count


def recompute_ladder(
    log_path: str | Path,
    *,
    frozen: set[str] | None = None,
    expected_digest: str | None = None,
) -> Ladder:
    """Replay the event log into a fresh Ladder — byte-identical recompute.

    Events of type 'register' add entrants; 'period' events carry a list of
    rating events applied as ONE Glicko-2 rating period.
    """
    elog = EventLog(log_path)
    elog.verify_chain(expected_digest=expected_digest)

    # Pre-scan log to find all quarantined battle IDs
    quarantined: set[str] = set()
    for event in elog.iter_events():
        if event.get("type") == "quarantine":
            bid = event.get("payload", {}).get("battle_id")
            if bid:
                quarantined.add(bid)

    ladder = Ladder()
    for event in elog.iter_events():
        payload = event["payload"]
        if event["type"] == "register":
            ladder.register(payload["name"], frozen=bool(payload.get("frozen", False)))
        elif event["type"] == "period":
            filtered = [
                RatingEvent(**ev)
                for ev in payload["events"]
                if ev.get("battle_id") not in quarantined
            ]
            if filtered:
                ladder.rate_period(filtered)
        elif event["type"] == "badge":
            agent_name = payload["agent_name"]
            badge = payload["badge"]
            if agent_name not in ladder.badges:
                ladder.badges[agent_name] = []
            if badge not in ladder.badges[agent_name]:
                ladder.badges[agent_name].append(badge)
    return ladder
