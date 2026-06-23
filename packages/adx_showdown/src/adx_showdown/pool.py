"""SidecarPool — partition battles across K sidecar processes (ADR-0012).

A battle is **share-nothing** — ``battle_id`` is the partition key, so each
battle is owned by exactly one sidecar (single-writer per partition) and turn
resolution stays a local transaction. The pool routes every op carrying a
``battle`` kwarg to that battle's owning sidecar; ``start`` assigns a new battle
to the **least-loaded** sidecar under its per-process cap. Battle-less ops
(``pack``/``import`` team validation) round-robin; ``rss`` aggregates.

Drop-in for the gateway's single :class:`Sidecar` — same
``start`` / ``stop`` / ``request`` / ``rss_mb`` surface — so wiring it in
(``sidecar_factory=lambda: SidecarPool(size=N)``) is a one-line gateway change.

Sizing: the load test (docs/references/2026-06-17-arena-loadtest-measured.md)
showed the per-sidecar limiter is single-threaded event-loop latency, not
memory, and that's a zero-think-time worst case — with realistic per-turn agent
think-time one sidecar holds many concurrent battles, so a small K (≈2-4) plus a
raised ``ADX_SIDECAR_MAX_OLD_SPACE_MB`` covers ~100 concurrent.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from adx_showdown.sidecar import Sidecar, SidecarError


class SidecarPool:
    """A pool of K :class:`Sidecar` processes, partitioned by ``battle_id``."""

    def __init__(self, size: int = 1, *, max_battles_per_sidecar: int | None = None) -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._sidecars: list[Sidecar] = [
            Sidecar(max_battles=max_battles_per_sidecar) for _ in range(size)
        ]
        self._cap = max_battles_per_sidecar
        self._owner: dict[str, Sidecar] = {}  # battle_id -> owning sidecar
        self._load: dict[int, int] = {}  # id(sidecar) -> live battle count
        self._rr = 0  # round-robin cursor for battle-less ops
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._sidecars)

    async def start(self) -> None:
        # Start all members concurrently, but if ANY fails after others came up,
        # tear the started ones back down so a partial start does not leak node
        # processes (PR #197 #3431602209). `Sidecar.stop()` is a no-op on a
        # member that never started, so a blanket stop is safe.
        results = await asyncio.gather(*(s.start() for s in self._sidecars), return_exceptions=True)
        failures = [r for r in results if isinstance(r, BaseException)]
        if failures:
            await asyncio.gather(*(s.stop() for s in self._sidecars), return_exceptions=True)
            raise failures[0]
        for s in self._sidecars:
            self._load[id(s)] = 0

    async def stop(self) -> None:
        await asyncio.gather(*(s.stop() for s in self._sidecars), return_exceptions=True)

    def _least_loaded(self) -> Sidecar | None:
        """The sidecar with the fewest live battles that is still under its cap."""
        best: Sidecar | None = None
        best_load: int | None = None
        for s in self._sidecars:
            if s.returncode is not None:
                # Never assign a new battle to a crashed member. Its live-battle
                # count is 0, so without this skip it looks MOST available and
                # would attract every new battle — the corpse-routing bug
                # (RECOVER-P1-sidecar-respawn). reclaim_dead() respawns it on touch.
                continue
            ld = self._load.get(id(s), 0)
            if self._cap is not None and ld >= self._cap:
                continue
            if best_load is None or ld < best_load:
                best, best_load = s, ld
        return best

    async def request(self, op: str, **kwargs: Any) -> dict[str, Any]:
        battle = kwargs.get("battle")

        # battle-less ops: team pack/import (stateless, any sidecar), rss (aggregate),
        # shutdown (broadcast).
        if battle is None:
            if op == "rss":
                return {"ok": True, "rss_mb": await self.rss_mb()}
            if op == "shutdown":
                results = await asyncio.gather(
                    *(s.request(op, **kwargs) for s in self._sidecars), return_exceptions=True
                )
                return {"ok": True, "shutdown": len(results)}
            s = self._sidecars[self._rr % len(self._sidecars)]
            self._rr += 1
            return await s.request(op, **kwargs)

        # battle-bound op: route to (or assign) the single owning sidecar.
        newly_reserved = False  # this call freshly recorded ownership for `battle`
        transient_replay = False  # this call reserved a transient (ownerless) load slot
        async with self._lock:
            if op == "start":
                s = self._owner.get(battle)
                if s is None:  # new battle — assign to the least-loaded sidecar
                    s = self._least_loaded()
                    if s is None:
                        # "capacity" keyword → gateway maps this to a retryable 503
                        raise SidecarError("arena at capacity (sidecar pool full)")
                    self._owner[battle] = s
                    self._load[id(s)] = self._load.get(id(s), 0) + 1
                    newly_reserved = True
            elif op == "replay":
                # A replay is a TRANSIENT, self-cleaning battle: the sidecar
                # creates it, re-simulates the inputLog, and deletes it all
                # within the one op (see sidecar.mjs `replay`). It carries a
                # `battle` kwarg but is owned by no one — the `/battle/{id}/dispute`
                # re-sim path would otherwise hit "not owned by any sidecar" in
                # pool mode (PR #197 #3431602204 / PR #198 #3431616702). Route it
                # to a sidecar with spare capacity and reserve a TRANSIENT `_load`
                # slot (no `_owner` row — nothing persists past the response).
                # The reservation is load-bearing: sidecar.mjs serializes every op
                # through a per-process FIFO, so without it a burst of dispute/audit
                # re-sims (which all see the same least-loaded sidecar) would queue
                # on ONE process and make the next `start` wait behind a long replay
                # while other members idle. Reserving spreads them (PR #203 #3431925699).
                s = self._least_loaded() or self._sidecars[self._rr % len(self._sidecars)]
                self._rr += 1
                self._load[id(s)] = self._load.get(id(s), 0) + 1
                transient_replay = True
            else:
                s = self._owner.get(battle)
                if s is None:
                    raise SidecarError(f"battle {battle!r} is not owned by any sidecar")

        # Release the battle's slot when it is over. Two completion paths:
        #   - an explicit `stop` op, OR
        #   - a `start`/`step` whose response carries `state.end` — the NORMAL
        #     arena path: the gateway publishes the receipt via `_finish` and
        #     never sends `stop`, and the Node sidecar has already deleted the
        #     ended battle internally. Without releasing here `_load` counts
        #     completed battles as live forever, so after size*cap battles
        #     `_least_loaded()` returns None and the pool reports permanent
        #     capacity exhaustion (false 503s) despite idle sidecars.
        # (`ended` starts True for `stop` so the slot is still freed even if the
        # stop request raises, preserving the prior finally-release behavior.)
        ended = op == "stop"
        try:
            resp = await s.request(op, **kwargs)
            ended = ended or bool((resp.get("state") or {}).get("end"))
            return resp
        except Exception:
            # A brand-new `start` REJECTED by the sidecar (a real error — no
            # battle was created) must not leak the reserved slot, or that
            # battle_id is wedged forever and capacity drips away (PR #197
            # #3431602213). Only roll back what THIS call reserved (not an
            # idempotent restart that found an existing owner). `ended` is still
            # False here, so the finally below won't double-release.
            #
            # NB: catch `Exception`, NOT `BaseException` — `asyncio.CancelledError`
            # (a BaseException) means the caller's task was cancelled, possibly
            # AFTER the start command already reached the sidecar and the battle
            # exists there. Rolling back then would desync the pool (load dropped)
            # from the sidecar (battle still counted), so the pool keeps routing
            # to a sidecar that's actually full and 503s while others idle
            # (PR #204 review). Let cancellation propagate with the reservation
            # intact, matching the sidecar; the turn-timer/forfeit rail reaps the
            # orphaned battle.
            if newly_reserved:
                async with self._lock:
                    if self._owner.pop(battle, None) is not None:
                        self._load[id(s)] = max(0, self._load.get(id(s), 0) - 1)
            raise
        finally:
            if transient_replay:
                # release the ownerless slot the replay reserved (always — on
                # success the replay battle is gone, on error the op is done too)
                async with self._lock:
                    self._load[id(s)] = max(0, self._load.get(id(s), 0) - 1)
            elif ended:
                async with self._lock:
                    if self._owner.pop(battle, None) is not None:
                        self._load[id(s)] = max(0, self._load.get(id(s), 0) - 1)

    async def rss_mb(self) -> float:
        """Total RSS across the pool (MB)."""
        vals = await asyncio.gather(*(s.rss_mb() for s in self._sidecars), return_exceptions=True)
        return round(sum(v for v in vals if isinstance(v, int | float)), 1)

    def any_dead(self) -> bool:
        """True if any pool member's node process has exited (a crashed sidecar).

        Synchronous + IPC-free — reads each member's cached ``returncode`` (``None``
        while running), so it is safe to call from the ``/healthz`` readiness probe
        without risking a hang on a wedged sidecar. A never-started member reports
        ``returncode is None`` (not dead). Auto-respawn is :meth:`reclaim_dead`;
        this only *reports* liveness.
        """
        return any(s.returncode is not None for s in self._sidecars)

    async def reclaim_dead(self) -> list[str]:
        """Touch-driven crash recovery: respawn any exited sidecar in place and
        evict the routes that pointed at it. Returns the evicted ``battle_id``s.

        Called ON TOUCH — the gateway's ``/healthz`` readiness probe + before a
        new battle is assigned — NOT a background reaper: the arena is
        sleeping-tolerant and all lifecycle runs on touch (the touch-driven
        doctrine). Idempotent: a fully live pool is a no-op (returns ``[]``).

        A crashed node process takes its in-process (share-nothing) battle state
        with it, so those battles are unrecoverable — their ``_owner`` rows are
        dropped (the battle_id then 404s on its next touch instead of routing into
        a dead pipe) and the member is replaced with a fresh :class:`Sidecar` so
        capacity is restored. The evicted ids are RETURNED so the gateway can fail
        those sessions closed (409 'interrupted') instead of leaving stale sessions
        that 400-loop on a battle whose sim state is gone (#2835).

        Concurrency (#2847): the fresh member is started OUTSIDE ``self._lock`` —
        ``Sidecar.start()`` can take seconds (Node spawn + ready handshake), and
        holding the lock across it would block ALL routing (``request`` /
        ``_least_loaded``) on the HEALTHY members for the whole respawn, turning one
        shard's crash into a global battle stall. The lock is held only for the
        synchronous swap, guarded by a slot re-check so a concurrent touch can't
        double-swap. Meanwhile ``_least_loaded`` already refuses to route new
        battles to the still-dead member, so nothing hits the corpse mid-respawn.
        """
        async with self._lock:
            dead = [(i, s) for i, s in enumerate(self._sidecars) if s.returncode is not None]
        evicted: list[str] = []
        for i, dead_s in dead:
            fresh = Sidecar(max_battles=self._cap)
            try:
                await fresh.start()  # OUTSIDE the lock — slow; healthy members keep routing
            except asyncio.CancelledError:
                # Caller cancelled mid-start; reap the half-spawned child, propagate.
                with contextlib.suppress(Exception):
                    await fresh.stop()
                raise
            except Exception:
                # Sidecar.start() can spawn the Node child and THEN raise (ready-event
                # timeout) without stopping it. Tear the half-started process down so a
                # failed respawn doesn't leak a Node child on every /healthz touch (the
                # any_dead() flag stays set → reclaim_dead re-runs each touch → OOM
                # spiral). The slot stays dead (any_dead stays True → /healthz still
                # 503s) and retries on the next touch.
                with contextlib.suppress(Exception):
                    await fresh.stop()
                # Even with no live replacement, the dead member's battle routes MUST
                # be evicted — otherwise reclaim_dead returns no IDs, the gateway
                # leaves those sessions live, and /choose keeps routing into the dead
                # pipe (opaque 400 instead of the intended 409 'interrupted') until
                # the container is recycled (PR #497 review PRRT_kwDOS0FXt86LqbQP).
                async with self._lock:
                    evicted.extend(b for b, o in self._owner.items() if o is dead_s)
                    self._owner = {b: o for b, o in self._owner.items() if o is not dead_s}
                continue
            # Post-start, pre-swap: `fresh` is a live Node child the caller now owns.
            # Any cancellation between here and the swap MUST reap it — otherwise the
            # spawned child is neither installed into `self._sidecars` nor stopped,
            # and the dead slot retries the respawn next touch (the slot stays dead),
            # leaking one Node process per cancellation (PR #497 review
            # PRRT_kwDOS0FXt86LqbQH). Track the outcome so the post-block cleanup
            # knows whether the swap landed.
            swapped_in = False
            try:
                async with self._lock:
                    # Slot re-check: a concurrent reclaim touch may have already
                    # swapped this slot while we were starting. Only swap if it's
                    # still the same corpse; otherwise our fresh member is redundant.
                    if self._sidecars[i] is dead_s:
                        evicted.extend(b for b, o in self._owner.items() if o is dead_s)
                        self._owner = {b: o for b, o in self._owner.items() if o is not dead_s}
                        self._load.pop(id(dead_s), None)
                        self._sidecars[i] = fresh
                        self._load[id(fresh)] = 0
                        swapped_in = True
            except BaseException:
                # CancelledError (or any post-start failure) here would orphan `fresh`
                # — reap it OUTSIDE the lock (Sidecar.stop() can block, and
                # request()/_least_loaded need the lock; #522 review P2) and re-raise.
                if not swapped_in:
                    with contextlib.suppress(Exception):
                        await fresh.stop()
                raise
            if not swapped_in:
                # Lost the slot re-check to a concurrent reclaim — reap the redundant
                # replacement OUTSIDE the lock: Sidecar.stop() can block on a graceful
                # shutdown + process exit, and request()/_least_loaded also need
                # self._lock — stopping under it would reintroduce the global routing
                # stall the start-outside-lock change fixed (#522 review P2).
                with contextlib.suppress(Exception):
                    await fresh.stop()
        return evicted
