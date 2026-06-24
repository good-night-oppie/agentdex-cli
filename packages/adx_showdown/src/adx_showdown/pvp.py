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
    # The OTHER player's agent_name (for session.opponent + pvp-choose identity).
    opponent_agent_name: str = ""
    # P2's claims_token_id — P1 stores this in the session for pvp-choose binding.
    p2_claims_token_id: str = ""
    # P2's pre-validated packed team (None = use starter pack).
    p2_team: str | None = None


@dataclass
class _WaiterMeta:
    fut: asyncio.Future[PvPPairing]
    agent_name: str
    token_id: str
    team: str | None


class PvPQueue:
    """FIFO asyncio matchmaker for UserAgent-vs-UserAgent mode.

    Callers await enqueue(); the second caller pairs both, resolves the
    first caller's future, and returns immediately.  cancel() removes a
    waiting owner and cancels their future.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        # owner_norm -> _WaiterMeta (future + identity metadata)
        self._waiters: dict[str, _WaiterMeta] = {}
        self._queue: list[str] = []  # FIFO order of owner_norms

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def enqueue(
        self,
        owner_norm: str,
        agent_name: str = "",
        token_id: str = "",
        team: str | None = None,
    ) -> PvPPairing:
        """Suspend until paired. Raises ValueError if owner already waiting."""
        loop = asyncio.get_running_loop()
        meta: _WaiterMeta | None = None

        async with self._get_lock():
            if owner_norm in self._waiters:
                raise ValueError(f"owner {owner_norm!r} is already in the PvP queue")
            if self._queue:
                p1_owner = self._queue.pop(0)
                p1_meta = self._waiters.pop(p1_owner)
                battle_id = f"pvp-{uuid.uuid4().hex[:10]}"
                # P1's pairing carries P2's identity so P1's session knows who P2 is.
                if not p1_meta.fut.done():
                    p1_meta.fut.set_result(
                        PvPPairing(
                            battle_id=battle_id,
                            role="p1",
                            opponent_owner=owner_norm,
                            opponent_agent_name=agent_name,
                            p2_claims_token_id=token_id,
                            p2_team=team,
                        )
                    )
                return PvPPairing(
                    battle_id=battle_id,
                    role="p2",
                    opponent_owner=p1_owner,
                    opponent_agent_name=p1_meta.agent_name,
                    p2_claims_token_id=token_id,
                    p2_team=team,
                )
            else:
                fut: asyncio.Future[PvPPairing] = loop.create_future()
                meta = _WaiterMeta(fut=fut, agent_name=agent_name, token_id=token_id, team=team)
                self._waiters[owner_norm] = meta
                self._queue.append(owner_norm)

        # Lock released — await the future that the next enqueue() will resolve.
        try:
            return await meta.fut
        except asyncio.CancelledError:
            self.cancel(owner_norm)
            raise

    def cancel(self, owner_norm: str) -> bool:
        """Remove owner from queue; cancel their future if unresolved."""
        if owner_norm in self._queue:
            self._queue.remove(owner_norm)
        wm = self._waiters.pop(owner_norm, None)
        if wm is not None and not wm.fut.done():
            wm.fut.cancel()
            return True
        return wm is not None

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
        # battle_id -> (pending Future or None, buffered choice or None, submitted marker)
        # The submitted marker rejects HTTP retries for the same pending P2 turn after
        # the policy consumes the choice but before the gateway publishes the next turn.
        self._state: dict[str, tuple[asyncio.Future[str] | None, str | None, bool]] = {}

    def make_p2_policy(self, battle_id: str):
        """Return an async Policy that waits for P2's explicit choice."""
        router = self

        async def _pvp_p2_policy(req, ctx=None):  # noqa: ARG001
            loop = asyncio.get_running_loop()
            _, buffered, _ = router._state.get(battle_id, (None, None, False))
            if buffered is not None:
                router._state[battle_id] = (None, None, True)
                return buffered
            fut: asyncio.Future[str] = loop.create_future()
            router._state[battle_id] = (fut, None, False)
            try:
                return await fut
            finally:
                cur_fut, cur_buf, cur_submitted = router._state.get(battle_id, (None, None, False))
                if cur_fut is fut:
                    router._state[battle_id] = (None, cur_buf, cur_submitted or fut.done())

        return _pvp_p2_policy

    def submit_p2_choice(self, battle_id: str, choice_str: str) -> bool:
        """P2 submits a choice. Returns True if the policy was awaiting it.

        Raises ValueError on a duplicate: a prior choice is already buffered or
        a resolved future hasn't been consumed yet by _advance.
        """
        fut, buffered, submitted = self._state.get(battle_id, (None, None, False))
        if submitted or buffered is not None:
            raise ValueError(
                f"duplicate P2 choice for {battle_id!r}: prior choice not yet consumed"
            )
        if fut is not None and fut.done():
            raise ValueError(
                f"duplicate P2 choice for {battle_id!r}: prior choice not yet consumed"
            )
        if fut is not None and not fut.done():
            fut.set_result(choice_str)
            self._state[battle_id] = (fut, None, True)
            return True
        # Buffer: policy not yet called (P2 chose before _advance ran)
        self._state[battle_id] = (None, choice_str, True)
        return False

    def has_unconsumed_p2_choice(self, battle_id: str) -> bool:
        """True if a prior P2 choice is still buffered or resolved-but-unconsumed — i.e. a
        fresh :meth:`submit_p2_choice` would raise the duplicate ``ValueError``. Read-only
        (no state mutation): lets the gateway reject a duplicate ``/pvp-choose`` retry
        BEFORE it writes a durable ``battle`` audit row, so a rejected choice never appears
        in replay/audit (#558 review). Mirrors the duplicate condition in submit_p2_choice.
        """
        fut, buffered, submitted = self._state.get(battle_id, (None, None, False))
        return submitted or buffered is not None or (fut is not None and fut.done())

    def is_waiting_for_p2(self, battle_id: str) -> bool:
        """True when _advance is suspended awaiting P2's choice."""
        fut, _, _ = self._state.get(battle_id, (None, None, False))
        return fut is not None and not fut.done()

    def mark_turn_advanced(self, battle_id: str) -> None:
        """Clear a consumed-choice marker once the gateway publishes the next turn."""
        fut, buffered, submitted = self._state.get(battle_id, (None, None, False))
        if fut is None and buffered is None and submitted:
            self._state.pop(battle_id, None)

    def cleanup(self, battle_id: str) -> None:
        """Release resources when a PvP battle ends."""
        fut, _, _ = self._state.pop(battle_id, (None, None, False))
        if fut is not None and not fut.done():
            fut.cancel()
