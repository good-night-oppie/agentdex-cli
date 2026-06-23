"""Touch-driven, bounded, in-memory rate-limiter + failure-lockout for the arena
auth surface (GA-AUTH security floor — ADX-Online Track A).

Why hand-rolled instead of slowapi/redis (doctrine fit):
  * NO background reaper. The arena is sleeping-tolerant (Koyeb suspends the
    container between requests), so all cleanup is LAZY, on request touch.
  * ``time.time()`` (wall clock), NOT ``time.monotonic()``: a microVM suspend can
    freeze CLOCK_MONOTONIC, so a monotonic-based lockout would never expire across
    a sleep. Wall-clock correctly accounts for the suspended interval on wake.
  * Bounded memory. An ``OrderedDict`` LRU with a hard ``capacity`` and force-
    eviction of the oldest entries — a volumetric attack (unique IPs / random
    emails) can never OOM the ~256MB nano; slowapi's unbounded ``MemoryStorage``
    would.
  * O(1) amortized per call: a dict touch + a short lazy-evict from the LRU front.

Each key (an IP or a normalized email) gets a token bucket plus a failure counter
that trips a lockout. Verdicts are computed without branching on whether the key
is "known", so the limiter cannot be used as a user-enumeration timing oracle.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable

# Indices into a key's mutable state list ``[tokens, last_touch, failures, lock_until]``.
_TOKENS, _LAST, _FAILS, _LOCK = 0, 1, 2, 3


class TouchDrivenRateLimiter:
    """A bounded token-bucket + failure-lockout, reaped lazily on touch.

    ``acquire(key)`` consumes one token and reports ``(rate_limited, locked_out)``.
    ``record_failure`` / ``record_success`` drive the lockout. Policy is fixed at
    construction so callers just pass the key (instantiate one limiter per policy,
    e.g. a per-IP volumetric limiter and a per-email brute-force limiter).
    """

    def __init__(
        self,
        *,
        max_tokens: float,
        refill_per_sec: float,
        max_failures: int = 0,
        lockout_sec: float = 0.0,
        capacity: int = 50_000,
        now: Callable[[], float] | None = None,
    ) -> None:
        if max_tokens <= 0 or refill_per_sec <= 0 or capacity < 1:
            raise ValueError("max_tokens and refill_per_sec must be > 0, capacity >= 1")
        self.max_tokens = float(max_tokens)
        self.refill_per_sec = float(refill_per_sec)
        self.max_failures = int(max_failures)
        self.lockout_sec = float(lockout_sec)
        self.capacity = int(capacity)
        # Injectable for tests; defaults to the wall clock (NOT monotonic — see module docstring).
        self._now = now or time.time
        self._store: OrderedDict[str, list[float]] = OrderedDict()

    def _touch(self, key: str, now: float) -> list[float]:
        state = self._store.get(key)
        if state is None:
            state = [self.max_tokens, now, 0.0, 0.0]
            self._store[key] = state  # appended at the MRU end
        else:
            self._store.move_to_end(key)  # O(1) mark most-recently-used
        return state

    def _evict_idle(self, now: float) -> None:
        # Lazy cleanup: drop fully-idle entries (token bucket refilled, not locked,
        # no failures) from the LRU front. Run BEFORE touching the current key so we
        # never evict the entry this call is about to operate on. An idle entry is
        # state-equivalent to a fresh one, so dropping + recreating it is lossless.
        while self._store:
            k = next(iter(self._store))
            s = self._store[k]
            refilled = s[_TOKENS] + (now - s[_LAST]) * self.refill_per_sec >= self.max_tokens
            if refilled and now >= s[_LOCK] and s[_FAILS] == 0:
                self._store.popitem(last=False)
            else:
                break

    def _enforce_cap(self) -> None:
        # Hard memory bound: force-evict the oldest (LRU front) until within
        # ``capacity``. Run AFTER touching the current key (it sits at the MRU end),
        # so the active key is never the one dropped — bounds memory under a
        # volumetric attack of unique keys without an OOM.
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)

    def acquire(self, key: str) -> tuple[bool, bool]:
        """Consume one token for ``key``. Returns ``(rate_limited, locked_out)``.

        Constant-time verdict (no branch on whether the key is known) so it can't
        leak user existence via timing.
        """
        now = self._now()
        self._evict_idle(now)
        state = self._touch(key, now)
        self._enforce_cap()
        if now < state[_LOCK]:
            return False, True
        # refill then consume one token
        state[_TOKENS] = min(
            self.max_tokens, state[_TOKENS] + (now - state[_LAST]) * self.refill_per_sec
        )
        state[_LAST] = now
        if state[_TOKENS] >= 1.0:
            state[_TOKENS] -= 1.0
            return False, False
        return True, False

    def record_failure(self, key: str) -> None:
        """Count a failed attempt for ``key``; trip the lockout at the threshold."""
        now = self._now()
        # Same bounded-touch cleanup as acquire(): the failure path also inserts new
        # keys, so a unique-key failure flood (random emails / codes) must run the
        # lazy evict + hard cap or it grows _store past ``capacity``, defeating the
        # memory bound this module guarantees.
        self._evict_idle(now)
        state = self._touch(key, now)
        self._enforce_cap()
        state[_FAILS] += 1.0
        if self.max_failures and state[_FAILS] >= self.max_failures:
            state[_LOCK] = now + self.lockout_sec
            state[_FAILS] = 0.0  # reset the window; the lock now gates access

    def record_success(self, key: str) -> None:
        """Clear failure + lockout state for ``key`` (e.g. on a successful login)."""
        state = self._store.get(key)
        if state is not None:
            state[_FAILS] = 0.0
            state[_LOCK] = 0.0
