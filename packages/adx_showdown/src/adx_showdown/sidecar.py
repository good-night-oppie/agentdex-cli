"""Async manager for the Node BattleStream sidecar (NDJSON over stdio).

One :class:`Sidecar` == one Node process multiplexing up to
``ADX_SIDECAR_MAX_BATTLES`` concurrent battles (ADR-0010 F1 — the stock
multi-process Showdown server is deleted from the design; this is the only
simulation surface).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PKG_ROOT = Path(__file__).resolve().parents[2]  # packages/adx_showdown/
SIDECAR_MJS = _PKG_ROOT / "sidecar.mjs"
NODE_MODULES = _PKG_ROOT / "node_modules" / "pokemon-showdown"


def sidecar_available() -> str | None:
    """Return a skip-reason string when the sidecar cannot run, else None."""
    if shutil.which("node") is None:
        return "node binary not on PATH"
    if not SIDECAR_MJS.is_file():
        return f"sidecar.mjs missing at {SIDECAR_MJS}"
    if not NODE_MODULES.is_dir():
        return f"pokemon-showdown not installed — run `npm install` in {_PKG_ROOT}"
    return None


class SidecarError(RuntimeError):
    """Sidecar returned ok=false or died."""


class Sidecar:
    """Drive one persistent sidecar process; id-matched requests + event queue."""

    def __init__(self, max_battles: int | None = None) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._max_battles = max_battles
        self.ready: dict[str, Any] | None = None

    async def __aenter__(self) -> Sidecar:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        reason = sidecar_available()
        if reason:
            raise SidecarError(reason)
        env = {  # minimal env — no secrets in the sidecar address space (A6/A7)
            "PATH": os.environ.get("PATH", ""),
            "NODE_ENV": "production",
        }
        if self._max_battles is not None:
            env["ADX_SIDECAR_MAX_BATTLES"] = str(self._max_battles)
        # pass the protocol-log caps through (else the sidecar default applies and
        # the knob is unreachable from a deployed gateway / a test). Both the line
        # cap and its companion byte cap (bounds the single-NDJSON replay response
        # under the 16 MiB readline limit).
        _proto_cap = os.environ.get("ADX_SIDECAR_MAX_PROTOCOL_LINES")
        if _proto_cap:
            env["ADX_SIDECAR_MAX_PROTOCOL_LINES"] = _proto_cap
        _proto_byte_cap = os.environ.get("ADX_SIDECAR_MAX_PROTOCOL_BYTES")
        if _proto_byte_cap:
            env["ADX_SIDECAR_MAX_PROTOCOL_BYTES"] = _proto_byte_cap
        # V8 old-space cap. Default 96 MB fits the 256 MB nano (one sidecar +
        # FastAPI gateway). On a multi-core box each pooled sidecar (ADR-0012
        # SidecarPool) gets its own process — raise this via the env knob so a
        # sidecar can hold more concurrent battles before GC pressure. The load
        # test (docs/references/2026-06-17-arena-loadtest-measured.md) showed RSS
        # pinned flat at the heap cap, so this is the per-sidecar memory lever.
        heap_mb = int(os.environ.get("ADX_SIDECAR_MAX_OLD_SPACE_MB", "96"))
        self._proc = await asyncio.create_subprocess_exec(
            "node",
            "--expose-gc",
            f"--max-old-space-size={heap_mb}",
            str(SIDECAR_MJS),
            cwd=str(_PKG_ROOT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            # One settle response (esp. `replay`, which returns the whole
            # battle's full protocol_log in a single NDJSON line) can far exceed
            # asyncio's default 64 KiB readline limit — a 90-turn battle is
            # ~1500 lines. Without this, readline() silently overruns and the
            # request hangs (measured: gen9randombattle replay stalled ~66s then
            # ProcessLookupError on teardown). 16 MiB covers any single battle.
            limit=16 * 1024 * 1024,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        # first line is the ready event
        ready = await asyncio.wait_for(self.events.get(), timeout=30)
        if ready.get("event") != "ready":
            raise SidecarError(f"unexpected first event: {ready}")
        self.ready = ready

    async def stop(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.returncode is None:
                try:
                    await asyncio.wait_for(self.request("shutdown"), timeout=5)
                except (TimeoutError, SidecarError):
                    self._proc.kill()
            await asyncio.wait_for(self._proc.wait(), timeout=10)
        finally:
            self._last_returncode = self._proc.returncode
            if self._reader_task:
                self._reader_task.cancel()
            self._proc = None

    _last_returncode: int | None = None

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode if self._proc else self._last_returncode

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(SidecarError("sidecar died"))
                self._pending.clear()
                await self.events.put({"event": "sidecar-exit"})
                return
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("sidecar non-json line: %r", raw[:200])
                continue
            if "id" in msg:
                # A response. If its request was cancelled/timed-out the future is
                # gone from _pending (or already resolved) — drop the late reply
                # instead of set_result-ing a done/cancelled future, which would
                # raise here and kill the reader, wedging the whole sidecar.
                fut = self._pending.pop(msg["id"], None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
            else:
                await self.events.put(msg)

    async def request(self, op: str, **kwargs: Any) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None:
            raise SidecarError("sidecar not started")
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        line = json.dumps({"id": rid, "op": op, **kwargs}) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()
        try:
            resp = await asyncio.wait_for(fut, timeout=60)
        except BaseException:
            # Cancellation (an outer wait_for — e.g. /metrics' 2s RSS budget —
            # timing us out) or our own 60s timeout must NOT leave the future in
            # _pending: _read_loop would later set_result the orphan when the slow
            # response arrives, raise on the cancelled future, and stop processing
            # every subsequent response. Drop it so a timeout can't wedge the sidecar.
            self._pending.pop(rid, None)
            raise
        if not resp.get("ok"):
            raise SidecarError(resp.get("error", "unknown sidecar error"))
        return resp

    async def rss_mb(self) -> float:
        resp = await self.request("rss")
        return float(resp["rss"]) / (1024 * 1024)
