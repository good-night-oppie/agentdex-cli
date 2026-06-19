"""test_arena_client — bounded retry of the arena's transient in-flight-forfeit 409.

When a battle times out while a concurrent caller is mid-forfeit, the arena's /state +
/choose return a 409 carrying a Retry-After header (opaque body). The shipped client must
re-poll a few times so the caller gets the ended timeout receipt instead of treating the
transient as terminal (arena PR #381 review 3443812758). A 409 WITHOUT Retry-After (e.g.
"no pending state") is terminal and must NOT be retried.
"""

from __future__ import annotations

import httpx
import pytest
from agentdex_cli.arena_client import _INFLIGHT_MAX_ATTEMPTS, ArenaClient


def _client_with(handler) -> ArenaClient:
    c = ArenaClient()
    # Retry-After: "0" → the bounded retry's sleep is 0s, so these stay fast.
    c._http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    return c


def test_battle_state_retries_inflight_409_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(409, headers={"Retry-After": "0"}, json={"detail": "arena error"})
        return httpx.Response(200, json={"status": "your_move", "battle_id": "b"})

    out = _client_with(handler).battle_state("tok", "b")
    assert calls["n"] == 2  # retried once
    assert out["status"] == "your_move"


def test_battle_choose_retries_inflight_409_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(409, headers={"Retry-After": "0"}, json={"detail": "arena error"})
        return httpx.Response(200, json={"status": "ended", "winner": "anchor-random"})

    out = _client_with(handler).battle_choose("tok", "b", 1)
    assert calls["n"] == 2
    assert out["status"] == "ended"  # the ended receipt, surfaced after the retry


def test_plain_409_without_retry_after_is_not_retried():
    """A non-retriable 409 (e.g. "no pending state") has no Retry-After → terminal."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(409, json={"detail": "arena error"})  # NO Retry-After

    with pytest.raises(httpx.HTTPStatusError):
        _client_with(handler).battle_state("tok", "b")
    assert calls["n"] == 1  # not retried


def test_inflight_retry_is_bounded():
    """A persistently-retriable 409 still terminates after the bounded attempt budget."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(409, headers={"Retry-After": "0"}, json={"detail": "arena error"})

    with pytest.raises(httpx.HTTPStatusError):
        _client_with(handler).battle_state("tok", "b")
    assert calls["n"] == _INFLIGHT_MAX_ATTEMPTS  # bounded, not infinite
