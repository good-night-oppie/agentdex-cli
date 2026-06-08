"""Gemini / Antigravity CLI bridge — cold-start each turn, conversation_id for continuity.

Per UP主 video: Antigravity CLI does NOT yet support ACP / long-lived JSON-RPC,
so every turn is a fresh subprocess. We keep continuity by passing the same
conversation_id (per workdir, or per caller-supplied session_id).

Expected CLI (placeholder — adjust to your installed Gemini/Antigravity binary):
  antigravity exec --conversation-id <id> --workdir <path> --prompt <text>
  → stdout: assistant text (or JSON if --output-format json is supported)

Override env:
  GEMINI_BIN=antigravity
  GEMINI_EXEC_SUBCMD=exec
  GEMINI_PROMPT_FLAG=--prompt
  GEMINI_CONV_FLAG=--conversation-id
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from base import (
    BridgeConfig,
    CliDead,
    LongRunningCliBridge,
    new_session_id,
    run_bridge,
)

log = logging.getLogger(__name__)

GEMINI_BIN = os.environ.get("GEMINI_BIN", "antigravity")
EXEC_SUBCMD = os.environ.get("GEMINI_EXEC_SUBCMD", "exec")
PROMPT_FLAG = os.environ.get("GEMINI_PROMPT_FLAG", "--prompt")
CONV_FLAG = os.environ.get("GEMINI_CONV_FLAG", "--conversation-id")


class GeminiBridge(LongRunningCliBridge):
    """No persistent stdio. Override lifecycle to skip subprocess + handshake."""

    def __init__(self, cfg: BridgeConfig):
        super().__init__(cfg)
        # Map workdir → last conversation_id for default continuity.
        self._conv_by_workdir: dict[str, str] = {}

    async def ensure_proc(self) -> None:
        return  # no long-lived process

    async def _handshake(self) -> None:
        return

    async def _kill(self) -> None:
        return

    def _resolve_conv(self, session_id: Optional[str], workdir: str) -> str:
        if session_id:
            return session_id
        if (existing := self._conv_by_workdir.get(workdir)):
            return existing
        new = new_session_id()
        self._conv_by_workdir[workdir] = new
        return new

    async def _run_once(self, prompt: str, conv_id: str, workdir: str, extra: dict) -> str:
        argv = [GEMINI_BIN, EXEC_SUBCMD, CONV_FLAG, conv_id, PROMPT_FLAG, prompt]
        if extra.get("output_json", True):
            # try common flag; harmless if unsupported (cold_shot will retry plain)
            argv += ["--output-format", "json"]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise CliDead(f"gemini cli failed ({proc.returncode}): {err.decode(errors='replace')[:400]}")
        text = out.decode(errors="replace")
        # Try parse JSON wrapper; fall through to raw.
        try:
            data = json.loads(text)
            return data.get("text") or data.get("result") or text
        except json.JSONDecodeError:
            return text

    async def _send_turn(self, prompt: str, *, session_id: Optional[str], extra: dict) -> str:
        workdir = extra.get("workdir") or self.cfg.workdir or os.getcwd()
        conv = self._resolve_conv(session_id, workdir)
        try:
            text = await self._run_once(prompt, conv, workdir, extra)
        except CliDead:
            raise
        self._conv_by_workdir[workdir] = conv
        # stash for caller via shared buffer? simplest: piggyback in result dict
        self._last_text = text
        return conv

    async def chat(self, prompt: str, *, session_id=None, extra=None) -> dict:
        extra = extra or {}
        try:
            new_sid = await self._send_turn(prompt, session_id=session_id, extra=extra)
            return {"ok": True, "session_id": new_sid, "text": self._last_text, "mode": "cold-per-turn"}
        except CliDead as e:
            if not self.cfg.allow_cold_fallback:
                return {"ok": False, "error": str(e)}
            # retry without --output-format json
            try:
                extra2 = {**extra, "output_json": False}
                new_sid = await self._send_turn(prompt, session_id=session_id, extra=extra2)
                return {"ok": True, "session_id": new_sid, "text": self._last_text, "mode": "cold-fallback-plain"}
            except CliDead as e2:
                return {"ok": False, "error": str(e2)}

    async def _cold_shot(self, prompt: str, *, session_id, extra) -> dict:
        # Not invoked separately — chat() already cold-runs each turn.
        raise NotImplementedError


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG", "INFO"))
    cfg = BridgeConfig(
        name="gemini",
        port=int(os.environ.get("GEMINI_BRIDGE_PORT", "49803")),
        workdir=os.environ.get("WORKDIR") or os.getcwd(),
        cli_argv=[GEMINI_BIN],
    )
    bridge = GeminiBridge(cfg)
    asyncio.run(run_bridge(bridge))


if __name__ == "__main__":
    main()
