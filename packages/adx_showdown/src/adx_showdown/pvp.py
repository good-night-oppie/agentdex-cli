"""PvP arena mode — UserAgent-vs-UserAgent matchmaking (GA-ARENA-MODES).

Two owners each call POST /me/battle/queue. PvPQueue pairs them FIFO: the
second caller resolves both futures immediately. PvPChoiceRouter lets P2
submit choices that P1's _advance loop awaits via a Policy callable — if P2
submits before _advance calls the policy, the choice is buffered.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PvPPairing:
    battle_id: str
    role: Literal["p1", "p2"]
    opponent_owner: str


class PvPQueue:
    """FIFO asyncio matchmaker for UserAgent-vs-UserAgent mode.

    Callers await enqueue(); the second caller pairs both, resolves the
    first caller's future, and returns immediately.  cancel() removes a
    waiting owner and cancels their future.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._waiters: dict[str, asyncio.Future[PvPPairing]] = {}
        self._queue: list[str] = []  # FIFO order of owner_norms

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def enqueue(self, owner_norm: str) -> PvPPairing:
        """Suspend until paired. Raises ValueError if owner already waiting."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[PvPPairing] | None = None

        async with self._get_lock():
            if owner_norm in self._waiters:
                raise ValueError(f"owner {owner_norm!r} is already in the PvP queue")
            if self._queue:
                p1_owner = self._queue.pop(0)
                p1_fut = self._waiters.pop(p1_owner)
                battle_id = f"pvp-{uuid.uuid4().hex[:10]}"
                if not p1_fut.done():
                    p1_fut.set_result(
                        PvPPairing(battle_id=battle_id, role="p1", opponent_owner=owner_norm)
                    )
                return PvPPairing(battle_id=battle_id, role="p2", opponent_owner=p1_owner)
            else:
                fut = loop.create_future()
                self._waiters[owner_norm] = fut
                self._queue.append(owner_norm)

        # Lock released — await the future that the next enqueue() will resolve.
        try:
            return await fut  # type: ignore[return-value]
        except asyncio.CancelledError:
            self.cancel(owner_norm)
            raise

    def cancel(self, owner_norm: str) -> bool:
        """Remove owner from queue; cancel their future if unresolved."""
        if owner_norm in self._queue:
            self._queue.remove(owner_norm)
        fut = self._waiters.pop(owner_norm, None)
        if fut is not None and not fut.done():
            fut.cancel()
            return True
        return fut is not None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)


class PvPChoiceRouter:
    """Routes P2 owner's explicit move choices to P1's _advance loop.

    P1's BattleSession uses ``make_p2_policy(battle_id)`` as its opponent
    Policy.  When _advance calls the policy (P2 has a pending request), it
    suspends until P2 submits via ``submit_p2_choice``.  If P2 submits
    *before* the policy is called, the choice is buffered and consumed on
    the next policy call.
    """

    def __init__(self) -> None:
        # battle_id -> (pending Future or None, buffered choice or None)
        self._state: dict[str, tuple[asyncio.Future[str] | None, str | None]] = {}

    def make_p2_policy(self, battle_id: str):
        """Return an async Policy that waits for P2's explicit choice."""
        router = self

        async def _pvp_p2_policy(req, ctx=None):  # noqa: ARG001
            loop = asyncio.get_running_loop()
            _, buffered = router._state.get(battle_id, (None, None))
            if buffered is not None:
                router._state[battle_id] = (None, None)
                return buffered
            fut: asyncio.Future[str] = loop.create_future()
            router._state[battle_id] = (fut, None)
            try:
                return await fut
            finally:
                cur_fut, cur_buf = router._state.get(battle_id, (None, None))
                if cur_fut is fut:
                    router._state[battle_id] = (None, cur_buf)

        return _pvp_p2_policy

    def submit_p2_choice(self, battle_id: str, choice_str: str) -> bool:
        """P2 submits a choice. Returns True if the policy was awaiting it."""
        fut, _ = self._state.get(battle_id, (None, None))
        if fut is not None and not fut.done():
            fut.set_result(choice_str)
            return True
        # Buffer: policy not yet called (P2 chose before _advance ran)
        self._state[battle_id] = (None, choice_str)
        return False

    def is_waiting_for_p2(self, battle_id: str) -> bool:
        """True when _advance is suspended awaiting P2's choice."""
        fut, _ = self._state.get(battle_id, (None, None))
        return fut is not None and not fut.done()

    def cleanup(self, battle_id: str) -> None:
        """Release resources when a PvP battle ends."""
        fut, _ = self._state.pop(battle_id, (None, None))
        if fut is not None and not fut.done():
            fut.cancel()
