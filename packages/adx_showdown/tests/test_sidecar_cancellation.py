"""Sidecar.request must be cancellation-safe so a timed-out request can't poison
the reader (PR #240 review).

/metrics wraps `sc.rss_mb()` in a 2s `asyncio.wait_for`. On timeout that cancels
the in-flight `request()`. If the request's future is left in `_pending`, the
`_read_loop` later `set_result`s it when the slow response finally arrives —
raising on the cancelled future and killing the reader, so every subsequent
request hangs (the sidecar is effectively wedged). These tests drive that path
with a fake process (no node needed).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from adx_showdown.sidecar import Sidecar


class _FakeStdin:
    def write(self, data: bytes) -> None:  # noqa: D401 — drains into the void
        pass

    async def drain(self) -> None:
        pass


class _FakeStdout:
    """A feedable line stream: tests push response bytes the reader consumes."""

    def __init__(self) -> None:
        self._q: asyncio.Queue[bytes] = asyncio.Queue()

    def feed(self, data: bytes) -> None:
        self._q.put_nowait(data)

    async def readline(self) -> bytes:
        return await self._q.get()


class _FakeProc:
    returncode = None

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout()


def test_request_cancellation_does_not_poison_reader():
    async def _run() -> None:
        sc = Sidecar()
        sc._proc = _FakeProc()  # type: ignore[assignment]
        sc._reader_task = asyncio.create_task(sc._read_loop())

        # Issue a request, then cancel it (an outer wait_for timing us out).
        req1 = asyncio.create_task(sc.request("rss"))
        await asyncio.sleep(0.01)  # request registers its future + writes the line
        assert 1 in sc._pending
        req1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await req1
        # The cancelled request removed its future — no orphan for _read_loop.
        assert 1 not in sc._pending

        # The slow response finally arrives. The reader must drop it, not crash.
        sc._proc.stdout.feed(json.dumps({"id": 1, "ok": True, "rss": 123456}).encode() + b"\n")
        await asyncio.sleep(0.01)
        assert not sc._reader_task.done(), "reader task was poisoned by the late response"

        # A subsequent request still resolves — the sidecar is not wedged.
        req2 = asyncio.create_task(sc.request("rss"))
        await asyncio.sleep(0.01)
        sc._proc.stdout.feed(json.dumps({"id": 2, "ok": True, "rss": 999}).encode() + b"\n")
        resp = await asyncio.wait_for(req2, timeout=1)
        assert resp["rss"] == 999

        sc._reader_task.cancel()

    asyncio.run(_run())
