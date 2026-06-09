"""rate_table unit tests (PR-W — Real cost end-to-end gap, partial close)."""

from __future__ import annotations

from adx_bridges.rate_table import estimate_cost_usd


def test_gpt_4o_rate_matches_yaml():
    """1M input + 1M output of gpt-4o → $2.50 + $10 = $12.50."""
    cost = estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000, 0)
    assert cost == 12.5


def test_gpt_4o_mini_rate_cheap():
    """1M input + 1M output of gpt-4o-mini → $0.15 + $0.60 = $0.75."""
    cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000, 0)
    assert cost == 0.75


def test_cached_tokens_use_cached_rate():
    """Cached tokens hit the cheaper cached_usd_per_1m rate."""
    base = estimate_cost_usd("gpt-4o", 1_000_000, 0, 0)
    cached = estimate_cost_usd("gpt-4o", 0, 0, 1_000_000)
    assert base == 2.5
    # cached_usd_per_1m for gpt-4o = 1.25
    assert cached == 1.25


def test_prefix_match_falls_through():
    """Specific model id like gpt-4o-2024-08-06 matches the gpt-4o prefix row."""
    cost = estimate_cost_usd("gpt-4o-2024-08-06", 1_000_000, 0, 0)
    assert cost == 2.5


def test_unknown_model_falls_through_to_codex_default():
    """Models not matching any prefix use codex-default fallback."""
    cost = estimate_cost_usd("some-mystery-model", 1_000_000, 1_000_000, 0)
    assert cost == 12.5  # = codex-default = gpt-4o rate


def test_zero_tokens_zero_cost():
    assert estimate_cost_usd("gpt-4o", 0, 0, 0) == 0.0


def test_none_model_uses_default():
    cost = estimate_cost_usd(None, 1_000_000, 0, 0)
    assert cost == 2.5  # codex-default


# ---------------------------------------------------------------------------
# claude bridge cold-shot list-frame regression (PR #15)
# ---------------------------------------------------------------------------


def test_claude_cold_shot_parses_json_array_output():
    """Regression: `claude -p ... --output-format json` returns a JSON ARRAY of
    frames (init / hook_started / hook_response / stream_event* / result), not
    a single object. Pre-PR-15 cold_shot did `json.loads(out).get('result')`
    which raised `AttributeError: 'list' object has no attribute 'get'` on
    every live cold-fallback. The fix walks the array and picks the terminal
    `type=result` frame. This test pins that contract by feeding a recorded
    (per PR #15 + PR #16 lint cleanup)

    array shape through the cold-shot parser logic in isolation.
    """
    import asyncio
    import json
    from unittest.mock import patch

    from adx_bridges.base import BridgeConfig
    from adx_bridges.claude_bridge import ClaudeBridge

    captured_array = [
        {"type": "system", "subtype": "init", "session_id": "abc-123"},
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}},
        },
        {
            "type": "result",
            "subtype": "success",
            "result": "Revenue $57.0B, Data Center $51.21B (source: nvidia-q3-fy2026-press-release.md:18)",
            "session_id": "abc-123",
            "total_cost_usd": 0.000123,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    ]
    json_array_bytes = json.dumps(captured_array).encode()

    cfg = BridgeConfig(name="claude", workdir="/tmp", cli_argv=["claude"])
    bridge = ClaudeBridge(cfg)

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return json_array_bytes, b""

    async def _run():
        with patch(
            "adx_bridges.claude_bridge.asyncio.create_subprocess_exec",
            new=lambda *a, **kw: _async_return(_FakeProc()),
        ):
            return await bridge._cold_shot("test prompt", session_id=None, extra={})

    async def _async_return(value):
        return value

    result = asyncio.run(_run())
    assert result["text"] == (
        "Revenue $57.0B, Data Center $51.21B (source: nvidia-q3-fy2026-press-release.md:18)"
    )
    assert result["session_id"] == "abc-123"
    assert bridge.last_cost_usd == 0.000123
    assert bridge.last_tokens == 30  # 10 + 20 + 0 + 0


def test_claude_cold_shot_handles_single_object_output():
    """Schema-drift defense: if claude ever switches to single-object json
    output, the parser still picks the object's `.result` field via the
    single-frame fallback. PR #15 wraps the parse so the live-bridge path
    is forward-compatible across the array/object split."""
    import asyncio
    import json
    from unittest.mock import patch

    from adx_bridges.base import BridgeConfig
    from adx_bridges.claude_bridge import ClaudeBridge

    single_obj_bytes = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": "single-frame shape",
            "session_id": "single-1",
        }
    ).encode()

    cfg = BridgeConfig(name="claude", workdir="/tmp", cli_argv=["claude"])
    bridge = ClaudeBridge(cfg)

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return single_obj_bytes, b""

    async def _run():
        with patch(
            "adx_bridges.claude_bridge.asyncio.create_subprocess_exec",
            new=lambda *a, **kw: _async_return(_FakeProc()),
        ):
            return await bridge._cold_shot("test prompt", session_id=None, extra={})

    async def _async_return(value):
        return value

    result = asyncio.run(_run())
    assert result["text"] == "single-frame shape"
    assert result["session_id"] == "single-1"
