"""Per-bridge NVIDIA-task probe (Phase-5 acceptance).

Each bridge must, on first turn, produce a response containing an
earnings-relevant substring (``revenue`` or ``gross margin``). Mocked-input
contract test always runs; live probes require ``ADX_LIVE_BRIDGES=1`` plus the
respective subscription CLI on PATH.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from adx_bridges import build_bridge
from adx_bridges.base import (
    BridgeConfig,
    LongRunningCliBridge,
    new_session_id,
)

TASK_ID = "nvidia-earnings-infographic"
EARNINGS_KEYWORDS = ("revenue", "gross margin", "data center", "billion")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tasks" / TASK_ID).is_dir():
            return parent
    pytest.skip(f"could not locate tasks/{TASK_ID}/ from {here}")


def _first_source_text() -> str:
    root = _repo_root()
    sources = sorted((root / "tasks" / TASK_ID / "sources").glob("*.md"))
    assert sources, f"no source files under tasks/{TASK_ID}/sources/"
    return sources[0].read_text(encoding="utf-8")[:4000]


def _build_prompt() -> str:
    body = _first_source_text()
    return (
        "Task: summarize the following source for an earnings infographic. "
        "Focus on revenue and gross margin claims. Reply concisely.\n\n"
        f"=== source ===\n{body}\n"
    )


# ---------------------------------------------------------------------------
# Mocked-input contract — always runs
# ---------------------------------------------------------------------------


class _MockNvidiaBridge(LongRunningCliBridge):
    """Stub bridge that echoes a keyword-rich response for contract testing."""

    def __init__(self):
        super().__init__(BridgeConfig(name="mock-nvidia", cli_argv=[]))

    async def ensure_proc(self):
        return

    async def _handshake(self):
        return

    async def _kill(self):
        return

    async def _send_turn(self, prompt, *, session_id, extra):
        text = (
            "Q3 FY2026 revenue jumped to $57B with a record gross margin in the "
            "data center segment driven by Blackwell GPU shipments."
        )
        self._last_response_text = text
        return session_id or new_session_id()

    async def _cold_shot(self, prompt, *, session_id, extra):
        raise NotImplementedError


def test_mock_bridge_keyword_contract():
    async def _run():
        b = _MockNvidiaBridge()
        return await b.send(_build_prompt())

    text, trace_id = asyncio.run(_run())
    assert text, "mock probe must return non-empty text"
    low = text.lower()
    assert any(k in low for k in EARNINGS_KEYWORDS), (
        f"expected one of {EARNINGS_KEYWORDS} in {text[:200]!r}"
    )
    assert trace_id is None or isinstance(trace_id, str)


def test_repo_root_resolves():
    root = _repo_root()
    assert (root / "tasks" / TASK_ID / "bundle.yaml").is_file()


# ---------------------------------------------------------------------------
# Live probes — opt-in
# ---------------------------------------------------------------------------


def _skip_unless_live(live: bool, has_cli: bool, name: str):
    if not live:
        pytest.skip(f"{name} live probe requires ADX_LIVE_BRIDGES=1")
    if not has_cli:
        pytest.skip(f"{name} CLI not on PATH")


def _assert_keywords(text: str, bridge_name: str):
    assert text, f"{bridge_name} produced empty response"
    low = text.lower()
    assert any(k in low for k in EARNINGS_KEYWORDS), (
        f"{bridge_name}: expected earnings keyword in response (first 300 chars): {text[:300]!r}"
    )


@pytest.mark.timeout(120)
def test_claude_nvidia_probe(live_bridges_enabled, has_claude_cli):
    _skip_unless_live(live_bridges_enabled, has_claude_cli, "claude")

    async def _run():
        b = build_bridge("claude")
        return await b.send(_build_prompt(), extra={"max_turns": 1})

    text, _ = asyncio.run(_run())
    _assert_keywords(text, "claude")


@pytest.mark.timeout(120)
def test_codex_nvidia_probe(live_bridges_enabled, has_codex_cli):
    _skip_unless_live(live_bridges_enabled, has_codex_cli, "codex")

    async def _run():
        b = build_bridge("codex")
        return await b.send(_build_prompt())

    text, _ = asyncio.run(_run())
    _assert_keywords(text, "codex")


@pytest.mark.xfail(
    reason="Phase-5 P5.5: codex-web fallback active; web flow is MVP shim only.",
    strict=False,
)
@pytest.mark.timeout(180)
def test_manus_nvidia_probe(live_bridges_enabled, has_codex_cli):
    _skip_unless_live(live_bridges_enabled, has_codex_cli, "manus(codex-web)")

    async def _run():
        b = build_bridge("manus")
        return await b.send(_build_prompt())

    text, _ = asyncio.run(_run())
    _assert_keywords(text, "manus(codex-web)")
