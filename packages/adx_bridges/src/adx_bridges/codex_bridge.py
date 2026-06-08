"""Codex app-server bridge — JSON-RPC-lite over stdio.

Spawn: codex app-server
Protocol (no "jsonrpc":"2.0" field; otherwise request/response/notification):
  client → initialize {capabilities:{experimentalApi:true}} → ack
  client → initialized (notification)
  client → thread/start {cwd}                      → {threadId}
  client → turn/start  {threadId, input:[{type:"text",text}]}
                                                   → {turnId} (immediate)
  server → turn/started
  server → item/started / item/agentMessage/delta / item/completed ...
  server → turn/completed {turnId, tokenUsage, finalState}
Server-initiated approval requests must be answered (auto-accept here).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from adx_bridges.base import (
    BridgeConfig,
    CliDead,
    LongRunningCliBridge,
    new_session_id,
    run_bridge,
)

log = logging.getLogger(__name__)

CODEX_BIN = os.environ.get("CODEX_BIN", "codex")


class CodexBridge(LongRunningCliBridge):
    def __init__(self, cfg: BridgeConfig):
        super().__init__(cfg)
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._thread_id: Optional[str] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._turn_buf: list[str] = []
        self._turn_done: Optional[asyncio.Event] = None
        self._turn_result: dict = {}
        # auto-accept approval policy (override via env)
        self.auto_accept = os.environ.get("CODEX_AUTO_APPROVE", "1") == "1"

    @classmethod
    def build_argv(cls) -> list[str]:
        return [CODEX_BIN, "app-server"]

    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _send_rpc(self, method: str, params: dict | None = None) -> dict:
        rid = self._alloc_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self._write_line({"id": rid, "method": method, "params": params or {}})
        return await fut

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        await self._write_line({"method": method, "params": params or {}})

    async def _handshake(self) -> None:
        self._reader_task = asyncio.create_task(self._reader_loop())
        init = await asyncio.wait_for(
            self._send_rpc(
                "initialize",
                {
                    "clientInfo": {"name": "adx_bridges.codex", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
            ),
            timeout=6.0,
        )
        log.info("codex initialized: %s", init.get("userAgent"))
        await self._send_notification("initialized")

    async def _reader_loop(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            while True:
                raw = await self.proc.stdout.readline()
                if not raw:
                    log.warning("codex stdout EOF")
                    self._fail_all_pending(CliDead("codex EOF"))
                    return
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    log.debug("non-json: %r", raw[:160])
                    continue
                await self._dispatch(msg)
        except asyncio.CancelledError:
            return

    def _fail_all_pending(self, exc: Exception) -> None:
        for f in self._pending.values():
            if not f.done():
                f.set_exception(exc)
        self._pending.clear()

    async def _dispatch(self, msg: dict) -> None:
        # Response (has "id" + ("result" or "error"), no "method")
        if "id" in msg and "method" not in msg:
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(CliDead(f"codex rpc error: {msg['error']}"))
                else:
                    fut.set_result(msg.get("result") or {})
            return

        method = msg.get("method")
        params = msg.get("params") or {}

        # Server-initiated approval requests (have "id")
        if "id" in msg and method and method.startswith("approval/"):
            decision = "accept" if self.auto_accept else "decline"
            await self._write_line({"id": msg["id"], "result": {"decision": decision}})
            return

        # Notifications
        if method == "turn/started":
            return
        if method and method.startswith("item/"):
            item = params.get("item") or {}
            if method == "item/agentMessage/delta":
                # delta is a raw string in current codex (0.137.0); handle dict shape too for older versions.
                delta = params.get("delta")
                if isinstance(delta, str):
                    self._turn_buf.append(delta)
                elif isinstance(delta, dict):
                    if (t := delta.get("text")):
                        self._turn_buf.append(t)
            elif method == "item/completed" and item.get("type") == "agentMessage":
                if (t := item.get("text")):
                    if not self._turn_buf:
                        self._turn_buf.append(t)
            return
        if method == "turn/completed":
            text = "".join(self._turn_buf)
            token_usage = params.get("tokenUsage") or {}
            tokens_total: Optional[int] = None
            if isinstance(token_usage, dict):
                # Codex 0.137 shape: {"inputTokens": N, "outputTokens": M,
                # "cachedInputTokens": K} (camelCase). Tolerate snake_case too.
                inp = (
                    token_usage.get("inputTokens")
                    or token_usage.get("input_tokens")
                    or 0
                )
                out = (
                    token_usage.get("outputTokens")
                    or token_usage.get("output_tokens")
                    or 0
                )
                cached = (
                    token_usage.get("cachedInputTokens")
                    or token_usage.get("cached_input_tokens")
                    or 0
                )
                tokens_total = int(inp + out + cached)
            self._turn_result = {
                "text": text,
                "turn_id": params.get("turnId"),
                "thread_id": self._thread_id,
                "token_usage": token_usage,
                "tokens_total": tokens_total,
            }
            self._last_response_text = text
            if tokens_total:
                self._last_tokens = tokens_total
            # Codex subscription does NOT surface a per-call dollar cost in
            # the result frame; orchestrator falls back to heuristic.
            self._turn_buf.clear()
            if self._turn_done:
                self._turn_done.set()
            return

    async def _send_turn(self, prompt: str, *, session_id: Optional[str], extra: dict) -> str:
        # session_id ↔ codex threadId. Field shape varies across codex versions
        # (`threadId` camelCase or `thread_id` snake_case); accept either.
        def _extract_tid(d: dict, fallback: Optional[str] = None) -> Optional[str]:
            if not isinstance(d, dict):
                return fallback
            # Direct keys first
            for k in ("threadId", "thread_id", "id"):
                if (v := d.get(k)):
                    return v
            # Nested {"thread": {"id": ...}} shape (current codex response)
            thread = d.get("thread")
            if isinstance(thread, dict):
                for k in ("id", "threadId", "thread_id"):
                    if (v := thread.get(k)):
                        return v
            elif isinstance(thread, str):
                return thread
            return fallback

        if session_id and session_id != self._thread_id:
            try:
                res = await self._send_rpc("thread/resume", {"threadId": session_id})
                self._thread_id = _extract_tid(res, session_id)
            except CliDead as e:
                log.warning("codex thread/resume failed: %s — starting fresh thread", e)
                self._thread_id = None
        if not self._thread_id:
            res = await self._send_rpc("thread/start", {"cwd": self.cfg.workdir})
            tid = _extract_tid(res)
            if not tid:
                raise CliDead(
                    f"codex thread/start returned no thread id; keys={list(res.keys())}"
                )
            self._thread_id = tid

        self._turn_done = asyncio.Event()
        self._turn_buf.clear()
        params = {
            "threadId": self._thread_id,
            "input": [{"type": "text", "text": prompt}],
        }
        for k in ("model", "cwd", "sandbox", "approvalPolicy"):
            if k in extra:
                params[k] = extra[k]
        await self._send_rpc("turn/start", params)
        await self._turn_done.wait()
        return self._thread_id

    async def _cold_shot(self, prompt: str, *, session_id: Optional[str], extra: dict) -> dict:
        # `codex exec` = one-shot non-interactive (requires git repo)
        argv = [CODEX_BIN, "exec", prompt]
        if extra.get("full_auto", True):
            argv.insert(2, "--full-auto")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cfg.workdir,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise CliDead(f"codex exec failed: {err.decode(errors='replace')[:400]}")
        text = out.decode(errors="replace")
        self._last_response_text = text
        return {"text": text, "session_id": None}


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG", "INFO"))
    cfg = BridgeConfig(
        name="codex",
        port=int(os.environ.get("CODEX_BRIDGE_PORT", "49802")),
        workdir=os.environ.get("WORKDIR") or os.getcwd(),
        cli_argv=CodexBridge.build_argv(),
    )
    bridge = CodexBridge(cfg)
    asyncio.run(run_bridge(bridge))


if __name__ == "__main__":
    main()
