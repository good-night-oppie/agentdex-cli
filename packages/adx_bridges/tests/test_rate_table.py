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
