"""Claude Code bridge — bidirectional stream-json over stdio.

CLI invocation (long-lived):
  claude -p ""
    --input-format stream-json
    --output-format stream-json
    --verbose
    --include-partial-messages
    --replay-user-messages
    --session-id <uuid>
    [--allowedTools ... --max-turns N --model sonnet ...]

Input frames (we write):  newline-delimited JSON, type=user with content blocks.
Output frames (we read):  newline-delimited JSON; types include
  system, assistant, user (replay), stream_event, result.
Turn ends when we see {"type":"result", ...} with session_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from adx_bridges.base import (
    BridgeConfig,
    CliDead,
    LongRunningCliBridge,
    new_session_id,
    run_bridge,
)

log = logging.getLogger(__name__)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


class ClaudeBridge(LongRunningCliBridge):
    def __init__(self, cfg: BridgeConfig):
        super().__init__(cfg)
        self.current_session_id: str | None = None
        self._turn_event = asyncio.Event()
        self._turn_result: dict = {}
        self._reader_task: asyncio.Task | None = None
        self._assistant_buf: list[str] = []

    @classmethod
    def build_argv(cls, session_id: str, extra: dict) -> list[str]:
        argv = [
            CLAUDE_BIN,
            "-p",
            "",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--replay-user-messages",
            "--session-id",
            session_id,
            "--dangerously-skip-permissions",
        ]
        if model := extra.get("model"):
            argv += ["--model", model]
        if tools := extra.get("allowed_tools"):
            argv += ["--allowedTools", ",".join(tools) if isinstance(tools, list) else tools]
        if mt := extra.get("max_turns"):
            argv += ["--max-turns", str(mt)]
        return argv

    async def _handshake(self) -> None:
        # Claude has no formal init frame in stream-json mode. First system frame is the greeting.
        self._reader_task = asyncio.create_task(self._reader_loop())
        # Wait for first system message ("type":"system","subtype":"init") to confirm ready.
        try:
            await asyncio.wait_for(self._await_initial_system(), timeout=8.0)
        except TimeoutError as e:
            raise CliDead("no init system frame from claude") from e

    async def _await_initial_system(self) -> None:
        self._init_seen = asyncio.Event()
        await self._init_seen.wait()

    async def _reader_loop(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            while True:
                raw = await self.proc.stdout.readline()
                if not raw:
                    log.warning("claude stdout EOF")
                    return
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    log.debug("non-json: %r", raw[:160])
                    continue
                await self._on_frame(frame)
        except asyncio.CancelledError:
            return

    async def _on_frame(self, frame: dict) -> None:
        ftype = frame.get("type")
        if ftype == "system" and not getattr(self, "_init_seen", None).is_set():
            self._init_seen.set()
            return
        if ftype == "stream_event":
            ev = frame.get("event") or {}
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta" and (t := delta.get("text")):
                self._assistant_buf.append(t)
            return
        if ftype == "assistant":
            # Final assistant message; could also derive text from content blocks.
            return
        if ftype == "result":
            text = "".join(self._assistant_buf) or frame.get("result") or ""
            cost_usd = frame.get("total_cost_usd")
            usage = frame.get("usage") or {}
            tokens_total: int | None = None
            if isinstance(usage, dict):
                inp = usage.get("input_tokens") or 0
                out = usage.get("output_tokens") or 0
                cache_creation = usage.get("cache_creation_input_tokens") or 0
                cache_read = usage.get("cache_read_input_tokens") or 0
                tokens_total = int(inp + out + cache_creation + cache_read)
            self._turn_result = {
                "text": text,
                "session_id": frame.get("session_id"),
                "num_turns": frame.get("num_turns"),
                "cost_usd": cost_usd,
                "subtype": frame.get("subtype"),
                "tokens_total": tokens_total,
            }
            self._last_response_text = text
            if cost_usd is not None:
                self._last_cost_usd = float(cost_usd)
            if tokens_total:
                self._last_tokens = tokens_total
            self._assistant_buf.clear()
            self._turn_event.set()

    async def _send_turn(self, prompt: str, *, session_id: str | None, extra: dict) -> str:
        # If caller requests a session change → respawn with that session_id.
        wanted_sid = session_id or self.current_session_id or new_session_id()
        if not self.current_session_id or wanted_sid != self.current_session_id:
            await self._respawn_for_session(wanted_sid, extra)

        self._turn_event.clear()
        self._assistant_buf.clear()
        await self._write_line(
            {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
            }
        )
        await self._turn_event.wait()
        new_sid = self._turn_result.get("session_id") or wanted_sid
        self.current_session_id = new_sid
        return new_sid

    async def _respawn_for_session(self, session_id: str, extra: dict) -> None:
        await self._kill()
        self.cfg.cli_argv = self.build_argv(session_id, extra)
        await self._spawn()
        self.current_session_id = session_id

    async def _cold_shot(self, prompt: str, *, session_id: str | None, extra: dict) -> dict:
        sid = session_id or new_session_id()
        argv = [
            CLAUDE_BIN,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--session-id",
            sid,
        ]
        if mt := extra.get("max_turns"):
            argv += ["--max-turns", str(mt)]
        if model := extra.get("model"):
            argv += ["--model", model]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cfg.workdir,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise CliDead(f"cold shot failed: {err.decode(errors='replace')[:400]}")
        try:
            result = json.loads(out)
            text = result.get("result") or ""
            sid_out = result.get("session_id")
        except json.JSONDecodeError:
            text = out.decode(errors="replace")
            sid_out = sid
        self._last_response_text = text
        self.current_session_id = sid_out or sid
        return {"text": text, "session_id": sid_out}


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG", "INFO"))
    sid = new_session_id()
    cfg = BridgeConfig(
        name="claude",
        port=int(os.environ.get("CLAUDE_BRIDGE_PORT", "49801")),
        workdir=os.environ.get("WORKDIR") or os.getcwd(),
        cli_argv=ClaudeBridge.build_argv(sid, {}),
    )
    bridge = ClaudeBridge(cfg)
    bridge.current_session_id = sid
    asyncio.run(run_bridge(bridge))


if __name__ == "__main__":
    main()
