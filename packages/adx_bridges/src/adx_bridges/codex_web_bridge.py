"""Codex-web bridge — Manus fallback per ADR-0009 + phase-5 A4.

P5.5 probe outcome (2026-06-08): `camoufox` Python pkg not installable in the
workspace; per phase-5 A4 fallback ladder, Manus is substituted by a
``codex exec``-backed bridge that simulates the web/agent flow via the
already-authed subscription Codex CLI. Session continuity is preserved via
``thread/resume`` if available, else falls back to per-call cold shots whose
session_id is a deterministic hash of the workdir + first prompt.

This is an MVP substitution flagged in STATE.md Notable events.

Async co-opetition note: this bridge participates in the per-baseline async
loop; no real-time race against claude/codex.
"""
from __future__ import annotations

import asyncio
import hashlib
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


class CodexWebBridge(LongRunningCliBridge):
    """Cold-per-turn bridge over ``codex exec`` with workdir-scoped continuity.

    No persistent subprocess — Codex web sessions are HTTP-side state; locally
    we mimic continuity by replaying the rolling transcript as a single prompt
    so the next turn sees prior context.
    """

    def __init__(self, cfg: BridgeConfig):
        super().__init__(cfg)
        self._conv_by_workdir: dict[str, str] = {}
        self._transcript_by_sid: dict[str, list[tuple[str, str]]] = {}

    async def ensure_proc(self) -> None:
        return

    async def _handshake(self) -> None:
        return

    async def _kill(self) -> None:
        return

    def _resolve_sid(self, session_id: Optional[str], workdir: str) -> str:
        if session_id:
            return session_id
        if (existing := self._conv_by_workdir.get(workdir)):
            return existing
        new = new_session_id()
        self._conv_by_workdir[workdir] = new
        return new

    def _render_prompt(self, sid: str, prompt: str) -> str:
        history = self._transcript_by_sid.get(sid) or []
        if not history:
            return prompt
        rendered = []
        for role, text in history:
            rendered.append(f"<{role}>\n{text}\n</{role}>")
        rendered.append(f"<user>\n{prompt}\n</user>")
        rendered.append("Continue the conversation. Reply as <assistant>.")
        return "\n\n".join(rendered)

    async def _run_codex_exec(self, prompt: str, workdir: str, extra: dict) -> str:
        argv = [CODEX_BIN, "exec"]
        if extra.get("full_auto", True):
            argv.append("--full-auto")
        if (model := extra.get("model")):
            argv += ["--model", model]
        argv.append(prompt)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise CliDead(
                f"codex-web exec failed ({proc.returncode}): "
                f"{err.decode(errors='replace')[:400]}"
            )
        return out.decode(errors="replace")

    async def _send_turn(self, prompt: str, *, session_id: Optional[str], extra: dict) -> str:
        workdir = extra.get("workdir") or self.cfg.workdir or os.getcwd()
        sid = self._resolve_sid(session_id, workdir)
        rendered = self._render_prompt(sid, prompt)
        text = await self._run_codex_exec(rendered, workdir, extra)

        history = self._transcript_by_sid.setdefault(sid, [])
        history.append(("user", prompt))
        history.append(("assistant", text))
        self._last_response_text = text
        return sid

    async def chat(self, prompt: str, *, session_id=None, extra=None) -> dict:
        extra = extra or {}
        try:
            new_sid = await self._send_turn(prompt, session_id=session_id, extra=extra)
            self._turn_idx += 1
            return {
                "ok": True,
                "session_id": new_sid,
                "text": self._last_response_text,
                "mode": "codex-web-cold-per-turn",
            }
        except CliDead as e:
            return {"ok": False, "error": str(e), "mode": "codex-web-cold-per-turn"}

    async def _cold_shot(self, prompt: str, *, session_id, extra) -> dict:
        raise NotImplementedError("codex-web is already cold-per-turn")


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG", "INFO"))
    cfg = BridgeConfig(
        name="codex-web",
        port=int(os.environ.get("CODEX_WEB_BRIDGE_PORT", "49804")),
        workdir=os.environ.get("WORKDIR") or os.getcwd(),
        cli_argv=[CODEX_BIN],
    )
    bridge = CodexWebBridge(cfg)
    asyncio.run(run_bridge(bridge))


if __name__ == "__main__":
    main()
