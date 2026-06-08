"""Long-running CLI bridge base.

Hermes (or any caller) → TCP JSON-RPC → bridge → CLI native protocol over stdio.
Keeps one CLI subprocess alive across many turns to skip cold-start cost.

Async co-opetition note (ADR-0009 §Amendment-2026-06-08): bridges are per-baseline
async actors invoked from the orchestrator's sequential loop; they do NOT race
in real-time against each other.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

try:
    from agentdex_observe import (
        get_trace_context_headers,
        is_enabled as _langfuse_is_enabled,
    )
except ImportError:  # pragma: no cover
    def get_trace_context_headers() -> dict[str, str]:
        return {}
    def _langfuse_is_enabled() -> bool:
        return False

log = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    name: str
    host: str = "127.0.0.1"
    port: int = 0
    workdir: Optional[str] = None
    cli_argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    spawn_timeout_sec: float = 10.0
    request_timeout_sec: float = 300.0
    allow_cold_fallback: bool = True


class CliDead(RuntimeError):
    pass


class LongRunningCliBridge(ABC):
    """Subclass overrides _handshake / _send_turn / _recv_until_done / _cold_shot."""

    def __init__(self, cfg: BridgeConfig):
        self.cfg = cfg
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._proc_lock = asyncio.Lock()
        self._req_lock = asyncio.Lock()
        self._stderr_task: Optional[asyncio.Task] = None
        self._handshake_done = False
        self._last_response_text: Optional[str] = None
        self._turn_idx: int = 0

    # ---- subprocess lifecycle ----

    async def ensure_proc(self) -> None:
        async with self._proc_lock:
            if self.proc and self.proc.returncode is None:
                return
            await self._spawn()

    async def _spawn(self) -> None:
        env = {**os.environ, **self.cfg.env}
        log.info("spawn %s argv=%s cwd=%s", self.cfg.name, self.cfg.cli_argv, self.cfg.workdir)
        self.proc = await asyncio.create_subprocess_exec(
            *self.cfg.cli_argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cfg.workdir,
            env=env,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self._handshake_done = False
        try:
            await asyncio.wait_for(self._handshake(), self.cfg.spawn_timeout_sec)
        except asyncio.TimeoutError as e:
            await self._kill()
            raise CliDead(f"handshake timeout: {self.cfg.name}") from e
        self._handshake_done = True

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        async for line in self.proc.stderr:
            log.debug("%s STDERR %s", self.cfg.name, line.decode(errors="replace").rstrip())

    async def _kill(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.send_signal(signal.SIGINT)
                await asyncio.wait_for(self.proc.wait(), 2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self.proc.kill()
                except ProcessLookupError:
                    pass
        self._handshake_done = False

    # ---- stdio framing helpers ----

    async def _write_line(self, obj: dict[str, Any]) -> None:
        assert self.proc and self.proc.stdin
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def _read_line(self) -> Optional[dict[str, Any]]:
        assert self.proc and self.proc.stdout
        line = await self.proc.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            log.warning("%s non-JSON stdout: %r", self.cfg.name, line[:200])
            return None

    # ---- subclass-implemented protocol ----

    @abstractmethod
    async def _handshake(self) -> None: ...

    @abstractmethod
    async def _send_turn(self, prompt: str, *, session_id: Optional[str], extra: dict) -> str: ...

    @abstractmethod
    async def _cold_shot(self, prompt: str, *, session_id: Optional[str], extra: dict) -> dict: ...

    # ---- public RPC entrypoint ----

    async def chat(self, prompt: str, *, session_id: Optional[str] = None,
                   extra: Optional[dict] = None) -> dict:
        extra = extra or {}
        async with self._req_lock:
            try:
                await self.ensure_proc()
                new_sid = await asyncio.wait_for(
                    self._send_turn(prompt, session_id=session_id, extra=extra),
                    self.cfg.request_timeout_sec,
                )
                self._turn_idx += 1
                return {
                    "ok": True,
                    "session_id": new_sid,
                    "text": self._last_response_text,
                    "mode": "long-lived",
                }
            except (CliDead, BrokenPipeError, ConnectionResetError, asyncio.TimeoutError) as e:
                log.warning("%s long-lived failed: %s — fallback", self.cfg.name, e)
                if not self.cfg.allow_cold_fallback:
                    return {"ok": False, "error": str(e), "mode": "long-lived"}
                await self._kill()
                result = await self._cold_shot(prompt, session_id=session_id, extra=extra)
                self._last_response_text = result.get("text")
                self._turn_idx += 1
                return {"ok": True, **result, "mode": "cold-fallback"}

    async def send(
        self,
        prompt: str,
        *,
        session_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> tuple[str, Optional[str]]:
        """Public bridge API (per phase-5 contract).

        Returns ``(response_text, langfuse_trace_id|None)``.

        Wraps :meth:`chat` in a Langfuse ``@trace_turn`` span so the orchestrator
        can stash the trace ref into the ResultCard. With ``LANGFUSE_PUBLIC_KEY``
        unset, the trace_id is ``None`` and bridge still works (no-op tracing).
        P5.4 contract: when ``extra["transport"] == "http"``, downstream HTTP
        callers SHOULD merge ``get_trace_context_headers()`` into their request
        headers so gateway-side spans re-parent under the Expedition trace.
        """
        merged_extra = {**(extra or {})}
        if merged_extra.get("transport") == "http":
            merged_extra.setdefault("trace_context_headers", get_trace_context_headers())

        trace_id: Optional[str] = None
        if _langfuse_is_enabled():
            from agentdex_observe import trace_turn

            sid_for_meta = session_id or "<new>"

            @trace_turn(
                name=f"{self.cfg.name}.send",
                metadata={
                    "bridge_name": self.cfg.name,
                    "session_id": sid_for_meta,
                    "turn_idx": self._turn_idx,
                    "model": merged_extra.get("model"),
                },
            )
            async def _wrapped() -> dict:
                return await self.chat(prompt, session_id=session_id, extra=merged_extra)

            result = await _wrapped()
            try:
                from agentdex_observe import current_trace_url
                url = current_trace_url()
                if url:
                    trace_id = url.rsplit("/", 1)[-1]
            except Exception:
                trace_id = None
        else:
            result = await self.chat(prompt, session_id=session_id, extra=merged_extra)

        if not result.get("ok"):
            raise CliDead(f"{self.cfg.name}.send failed: {result.get('error')}")
        return (result.get("text") or "", trace_id)


# ---------------------------------------------------------------------------
# TCP JSON-RPC server (newline-delimited)
# ---------------------------------------------------------------------------

class JsonRpcServer:
    def __init__(self, bridge: LongRunningCliBridge):
        self.bridge = bridge
        self._methods: dict[str, Callable[[dict], Awaitable[Any]]] = {
            "chat": self._chat,
            "ping": self._ping,
            "stop": self._stop,
        }

    async def _chat(self, params: dict) -> dict:
        return await self.bridge.chat(
            params["prompt"],
            session_id=params.get("session_id"),
            extra=params.get("extra") or {},
        )

    async def _ping(self, _params: dict) -> dict:
        return {"pong": True, "name": self.bridge.cfg.name, "ts": time.time()}

    async def _stop(self, _params: dict) -> dict:
        await self.bridge._kill()
        return {"stopped": True}

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("client connect %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                try:
                    req = json.loads(line)
                except json.JSONDecodeError:
                    writer.write(b'{"error":"bad json"}\n')
                    await writer.drain()
                    continue
                rid = req.get("id")
                method = req.get("method")
                params = req.get("params") or {}
                fn = self._methods.get(method)
                if not fn:
                    resp = {"id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}}
                else:
                    try:
                        result = await fn(params)
                        resp = {"id": rid, "result": result}
                    except Exception as e:
                        log.exception("rpc fail")
                        resp = {"id": rid, "error": {"code": -32000, "message": repr(e)}}
                writer.write((json.dumps(resp, ensure_ascii=False) + "\n").encode())
                await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def serve(self) -> None:
        cfg = self.bridge.cfg
        server = await asyncio.start_server(self._handle_client, cfg.host, cfg.port)
        sock = server.sockets[0].getsockname()
        log.info("%s bridge listening on tcp://%s:%s", cfg.name, sock[0], sock[1])
        async with server:
            await server.serve_forever()


# ---------------------------------------------------------------------------
# entrypoint helper
# ---------------------------------------------------------------------------

async def run_bridge(bridge: LongRunningCliBridge) -> None:
    server = JsonRpcServer(bridge)
    try:
        await bridge.ensure_proc()
    except Exception as e:
        log.warning("eager spawn failed (will lazy-spawn on first chat): %s", e)
    await server.serve()


def new_session_id() -> str:
    return str(uuid.uuid4())
