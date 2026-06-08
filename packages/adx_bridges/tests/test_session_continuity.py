"""Session-id continuity tests for adx_bridges (Phase-5 acceptance).

Each bridge is exercised in TWO turns; the second turn must reference content
from the first. Live subscription-CLI calls run only when ``ADX_LIVE_BRIDGES=1``
AND the CLI binary is on PATH; otherwise tests are SKIPPED (not failed),
documented per phase-5 spec.

A mocked-bridge continuity test guarantees the API contract itself is sound
even when no subscription auth is available in CI.
"""
from __future__ import annotations

import asyncio

import pytest

from adx_bridges import build_bridge
from adx_bridges.base import (
    BridgeConfig,
    LongRunningCliBridge,
    new_session_id,
)


# ---------------------------------------------------------------------------
# Mocked-bridge contract check — runs in every environment
# ---------------------------------------------------------------------------


class _MockBridge(LongRunningCliBridge):
    """Deterministic in-process bridge for contract testing."""

    def __init__(self):
        super().__init__(BridgeConfig(name="mock", cli_argv=[]))
        self._sid: str | None = None
        self._history: list[tuple[str, str]] = []

    async def ensure_proc(self): return
    async def _handshake(self): return
    async def _kill(self): return

    async def _send_turn(self, prompt, *, session_id, extra):
        sid = session_id or self._sid or new_session_id()
        self._sid = sid
        prior_prompts = " | ".join(p for p, _ in self._history) or "<none>"
        echo = (
            f"[turn {len(self._history)+1}] Current: {prompt!r}. "
            f"Earlier prompts: {prior_prompts}."
        )
        self._history.append((prompt, echo))
        self._last_response_text = echo
        return sid

    async def _cold_shot(self, prompt, *, session_id, extra):
        raise NotImplementedError


def test_mock_bridge_session_continuity():
    """API contract: send() returns (text, trace_id|None); sid stable across turns."""

    async def _run():
        b = _MockBridge()
        t1, tr1 = await b.send("hello first turn", session_id="sid-fixed")
        t2, tr2 = await b.send("what did I just say?", session_id="sid-fixed")
        return b, t1, t2, tr1, tr2

    b, t1, t2, tr1, tr2 = asyncio.run(_run())

    assert b._sid == "sid-fixed", "session_id must remain stable across turns"
    assert "turn 1" in t1
    assert "turn 2" in t2
    assert "hello first turn" in t2, "turn 2 must reference turn 1 prompt"
    # trace_id is None when LANGFUSE_PUBLIC_KEY unset; non-None when set
    assert tr1 is None or isinstance(tr1, str)
    assert tr2 is None or isinstance(tr2, str)


# ---------------------------------------------------------------------------
# Live subscription-CLI tests — opt-in via ADX_LIVE_BRIDGES=1
# ---------------------------------------------------------------------------


def _skip_unless_live(live: bool, has_cli: bool, name: str):
    if not live:
        pytest.skip(f"{name} continuity test requires ADX_LIVE_BRIDGES=1")
    if not has_cli:
        pytest.skip(f"{name} CLI not on PATH")


@pytest.mark.timeout(120)
def test_claude_session_continuity(live_bridges_enabled, has_claude_cli):
    _skip_unless_live(live_bridges_enabled, has_claude_cli, "claude")

    async def _run():
        b = build_bridge("claude")
        sid = b.current_session_id
        t1, _ = await b.send(
            "Hello! Remember the word 'rosebud'. What is your session id?",
            session_id=sid,
        )
        t2, _ = await b.send("What word did I ask you to remember?", session_id=sid)
        await b._kill()
        return t1, t2

    t1, t2 = asyncio.run(_run())
    assert t1, "turn 1 response must be non-empty"
    assert t2, "turn 2 response must be non-empty"
    assert "rosebud" in t2.lower(), f"turn 2 must reference turn 1 (got {t2[:200]!r})"


@pytest.mark.timeout(120)
def test_codex_session_continuity(live_bridges_enabled, has_codex_cli):
    _skip_unless_live(live_bridges_enabled, has_codex_cli, "codex")

    async def _run():
        b = build_bridge("codex")
        t1, _ = await b.send(
            "Hello! Remember the word 'rosebud'. What is your thread id?"
        )
        # Codex assigns thread_id on first turn; re-use it for turn 2
        sid = getattr(b, "_thread_id", None)
        t2, _ = await b.send("What word did I ask you to remember?", session_id=sid)
        await b._kill()
        return t1, t2

    t1, t2 = asyncio.run(_run())
    assert t1, "turn 1 response must be non-empty"
    assert t2, "turn 2 response must be non-empty"
    assert "rosebud" in t2.lower(), f"turn 2 must reference turn 1 (got {t2[:200]!r})"


@pytest.mark.xfail(
    reason="Phase-5 P5.5: camoufox absent → codex-web fallback; web session "
    "continuity is best-effort via transcript replay only (browser auth flow "
    "not implemented in MVP).",
    strict=False,
)
@pytest.mark.timeout(180)
def test_manus_session_continuity(live_bridges_enabled, has_codex_cli):
    _skip_unless_live(live_bridges_enabled, has_codex_cli, "manus(codex-web)")

    async def _run():
        b = build_bridge("manus")
        t1, _ = await b.send(
            "Hello! Remember the word 'rosebud'. What is your session id?"
        )
        t2, _ = await b.send("What word did I ask you to remember?")
        return t1, t2

    t1, t2 = asyncio.run(_run())
    assert t1 and t2
    assert "rosebud" in t2.lower()
