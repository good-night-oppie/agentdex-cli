"""TouchDrivenRateLimiter (GA-AUTH security floor): token bucket, wall-clock
lockout that survives a container 'sleep', lazy + bounded eviction."""

from __future__ import annotations

import pytest
from agentdex_arena.limiter import TouchDrivenRateLimiter


class _Clock:
    """Injectable wall clock the limiter reads instead of time.time()."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_token_bucket_allows_burst_then_rate_limits():
    clk = _Clock()
    lim = TouchDrivenRateLimiter(max_tokens=3, refill_per_sec=1e-6, now=clk)
    assert lim.acquire("ip") == (False, False)
    assert lim.acquire("ip") == (False, False)
    assert lim.acquire("ip") == (False, False)
    assert lim.acquire("ip") == (True, False)  # 4th in the burst → rate limited


def test_touch_recovery_refills_without_a_reaper():
    clk = _Clock()
    lim = TouchDrivenRateLimiter(max_tokens=1, refill_per_sec=1.0, now=clk)
    assert lim.acquire("ip") == (False, False)
    assert lim.acquire("ip") == (True, False)  # bucket empty
    clk.advance(2.0)  # 2s passes (or the container slept 2s)
    assert lim.acquire("ip") == (False, False)  # refilled lazily on the next touch


def test_failure_lockout_then_wall_clock_expiry():
    clk = _Clock()
    lim = TouchDrivenRateLimiter(
        max_tokens=100, refill_per_sec=1.0, max_failures=3, lockout_sec=900.0, now=clk
    )
    for _ in range(3):
        lim.record_failure("user@x")
    assert lim.acquire("user@x") == (False, True)  # locked out
    clk.advance(901.0)  # wall-clock advances past the lockout (survives a suspend)
    assert lim.acquire("user@x") == (False, False)  # lock expired
    # a fresh success clears any residual failure state
    lim.record_success("user@x")


def test_memory_is_hard_bounded_under_a_volumetric_attack():
    lim = TouchDrivenRateLimiter(max_tokens=1, refill_per_sec=1e-9, capacity=100)
    for i in range(500):  # 5x capacity of distinct keys (no refill → all stay "active")
        lim.acquire(f"ip-{i}")
    assert len(lim._store) <= 100  # force-eviction kept it bounded — no OOM


def test_failure_path_is_also_hard_bounded_under_a_volumetric_attack():
    # The brute-force path inserts keys too; a unique-email/code failure flood must
    # obey the same hard cap as acquire() or it grows _store past capacity (OOM).
    lim = TouchDrivenRateLimiter(
        max_tokens=1, refill_per_sec=1e-9, max_failures=3, lockout_sec=900.0, capacity=100
    )
    for i in range(500):  # 5x capacity of distinct failing keys
        lim.record_failure(f"user-{i}@x")
    assert len(lim._store) <= 100  # failure path force-evicts the LRU front too


def test_idle_entries_are_lazily_evicted_on_touch():
    clk = _Clock()
    lim = TouchDrivenRateLimiter(max_tokens=2, refill_per_sec=1.0, now=clk)
    lim.acquire("old")
    clk.advance(10.0)  # "old" fully refills + is unlocked + has no failures → idle
    lim.acquire("new")  # touching the limiter sweeps the idle front entry
    assert "old" not in lim._store
    assert "new" in lim._store


def test_known_and_unknown_keys_take_the_same_path():
    # constant-time verdict: acquiring a brand-new key and a seen key both return
    # the same shape with no existence-dependent branch (anti-enumeration).
    clk = _Clock()
    lim = TouchDrivenRateLimiter(max_tokens=5, refill_per_sec=1.0, now=clk)
    assert lim.acquire("seen") == (False, False)
    assert lim.acquire("seen") == (False, False)
    assert lim.acquire("never-seen-before") == (False, False)


@pytest.mark.parametrize(
    "bad",
    [
        {"max_tokens": 0},
        {"refill_per_sec": 0},
        {"capacity": 0},
        # lockout enabled by a threshold but with a non-positive duration would
        # silently disable brute-force lockout (lock_until <= now) — reject it.
        {"max_failures": 3},  # lockout_sec defaults to 0.0
        {"max_failures": 3, "lockout_sec": 0.0},
        {"max_failures": 1, "lockout_sec": -5.0},
    ],
)
def test_rejects_invalid_policy(bad):
    kw = {"max_tokens": 1.0, "refill_per_sec": 1.0, "capacity": 10}
    kw.update(bad)
    with pytest.raises(ValueError):
        TouchDrivenRateLimiter(**kw)


def test_accepts_threshold_with_positive_lockout():
    # the valid counterpart: a non-zero threshold WITH a positive lockout is fine
    TouchDrivenRateLimiter(max_tokens=1.0, refill_per_sec=1.0, max_failures=3, lockout_sec=1.0)
