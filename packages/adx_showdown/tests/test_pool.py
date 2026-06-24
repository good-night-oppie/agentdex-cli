"""SidecarPool routing tests (ADR-0012) — no real node process; FakeSidecar."""

from __future__ import annotations

import asyncio

import pytest
from adx_showdown import pool as pool_mod
from adx_showdown.pool import SidecarPool
from adx_showdown.sidecar import SidecarError


class FakeSidecar:
    """In-memory stand-in for Sidecar — records ops, no subprocess."""

    instances: list[FakeSidecar] = []

    def __init__(self, max_battles: int | None = None) -> None:
        self.max_battles = max_battles
        self.started = False
        self.ops: list[tuple[str, dict]] = []
        self._rss = 12.0
        self.returncode: int | None = None  # None = alive; set to simulate a crash
        FakeSidecar.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def request(self, op: str, **kw):
        self.ops.append((op, kw))
        return {"ok": True, "op": op, **kw}

    async def rss_mb(self) -> float:
        return self._rss


@pytest.fixture(autouse=True)
def _patch_sidecar(monkeypatch):
    FakeSidecar.instances = []
    monkeypatch.setattr(pool_mod, "Sidecar", FakeSidecar)


def _run(coro):
    return asyncio.run(coro)


def test_start_starts_all_sidecars():
    p = SidecarPool(size=3)
    _run(p.start())
    assert p.size == 3
    assert all(s.started for s in FakeSidecar.instances)


def test_start_stops_already_started_on_partial_failure():
    """If one member fails to start, the ones already up are torn back down so
    we don't leak node processes. PR #197 #3431602209."""
    p = SidecarPool(size=3)

    async def boom() -> None:
        raise RuntimeError("node spawn failed")

    p._sidecars[1].start = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="node spawn failed"):
        _run(p.start())
    # every member was stopped (the two that started + the no-op on the failed one)
    assert all(not s.started for s in p._sidecars)
    # no load recorded since startup did not complete
    assert p._load == {}


def test_failed_start_rolls_back_ownership():
    """A start that records ownership then fails in the sidecar must roll the
    reservation back — the battle_id must not be wedged. PR #197 #3431602213."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        s = p._sidecars[0]

        async def boom(op, **kw):
            raise SidecarError("sidecar rejected start")

        s.request = boom  # type: ignore[method-assign]
        with pytest.raises(SidecarError, match="rejected start"):
            await p.request("start", battle="b1")
        # ownership + load rolled back to pristine
        assert "b1" not in p._owner
        assert p._load.get(id(s), 0) == 0

    _run(go())


def test_idempotent_restart_failure_does_not_double_rollback():
    """A failing op on an ALREADY-owned battle must NOT decrement load (this call
    reserved nothing). Guards the newly_reserved flag."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")  # reserve once
        s = p._owner["b1"]
        assert p._load[id(s)] == 1

        async def boom(op, **kw):
            raise SidecarError("transient")

        s.request = boom  # type: ignore[method-assign]
        with pytest.raises(SidecarError):
            await p.request("start", battle="b1")  # restart same battle, fails
        # still owned, load intact — the failed call reserved nothing to roll back
        assert p._owner.get("b1") is s
        assert p._load[id(s)] == 1

    _run(go())


def test_cancelled_start_keeps_reservation():
    """A CancelledError mid-start (client disconnect / timeout) must NOT roll the
    reservation back — the sidecar may have already created the battle, so the
    pool must stay consistent with it instead of routing to a now-full sidecar.
    PR #204 review."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        s = p._sidecars[0]

        async def cancel_mid_start(op, **kw):
            raise asyncio.CancelledError()

        s.request = cancel_mid_start  # type: ignore[method-assign]
        with pytest.raises(asyncio.CancelledError):
            await p.request("start", battle="b1")
        # reservation preserved (matches the sidecar's likely-created battle)
        assert p._owner.get("b1") is s
        assert p._load[id(s)] == 1

    _run(go())


def test_start_spreads_battles_to_least_loaded():
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1", format="gen9ou")
        await p.request("start", battle="b2", format="gen9ou")

    _run(go())
    # two battles → one on each sidecar (least-loaded spreads them)
    owners = {id(p._owner["b1"]), id(p._owner["b2"])}
    assert len(owners) == 2


def test_step_and_stop_route_to_owner_then_free():
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        owner = p._owner["b1"]
        await p.request("step", battle="b1", choices={"p1": "move 1"})
        # the step went to the SAME sidecar that owns b1
        assert ("step", {"battle": "b1", "choices": {"p1": "move 1"}}) in owner.ops
        await p.request("stop", battle="b1")
        # stop frees the assignment
        assert "b1" not in p._owner
        assert p._load[id(owner)] == 0

    _run(go())


def test_completion_via_state_end_frees_slot_without_stop():
    """The NORMAL arena path: a step whose response carries ``state.end`` frees
    the pool slot WITHOUT a `stop` (the sidecar already deleted the battle and
    the gateway publishes via `_finish`). PR#197 #3431602199 / PR#198 #3431616695.
    """
    p = SidecarPool(size=1, max_battles_per_sidecar=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        owner = p._owner["b1"]
        assert p._load[id(owner)] == 1

        # make ONLY the step end the battle (subsequent starts stay normal)
        async def ending_on_step(op, **kw):
            owner.ops.append((op, kw))
            if op == "step":
                return {"ok": True, "state": {"end": {"winner": "p1", "turns": 3}}}
            return {"ok": True, "op": op, **kw}

        owner.request = ending_on_step  # type: ignore[method-assign]
        await p.request("step", battle="b1", choices={"p1": "move 1"})
        # freed without any stop op
        assert "b1" not in p._owner
        assert p._load[id(owner)] == 0
        # capacity recovered: a new battle starts on the now-idle sidecar
        await p.request("start", battle="b2")
        assert "b2" in p._owner

    _run(go())


def test_completed_battles_do_not_exhaust_capacity():
    """Regression: running size*cap battles to completion (each via a state.end
    step, no stop) must NOT permanently fill the pool."""
    p = SidecarPool(size=2, max_battles_per_sidecar=2)
    _run(p.start())

    async def go():
        for i in range(6):  # 3× the size*cap=4 capacity, serially
            bid = f"b{i}"
            await p.request("start", battle=bid)
            owner = p._owner[bid]

            async def ending_on_step(op, **kw):
                return (
                    {"ok": True, "state": {"end": {"winner": "p1"}}}
                    if op == "step"
                    else {"ok": True}
                )

            owner.request = ending_on_step  # type: ignore[method-assign]
            await p.request("step", battle=bid, choices={})
        # every battle released → pool fully idle, no _load leak
        assert all(p._load[id(s)] == 0 for s in FakeSidecar.instances)
        assert p._owner == {}

    _run(go())


def test_step_unknown_battle_raises():
    p = SidecarPool(size=1)
    _run(p.start())
    with pytest.raises(SidecarError):
        _run(p.request("step", battle="ghost"))


def test_replay_routes_to_unowned_sidecar():
    """A `replay` is a transient self-cleaning battle — it must route WITHOUT a
    prior owner (the /battle/{id}/dispute re-sim path in pool mode). It records
    no ownership and leaks no load. PR#197 #3431602204 / PR#198 #3431616702."""
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        lines = [">start {}", ">p1 move 1"]
        resp = await p.request("replay", battle="d1", lines=lines)  # no prior start
        assert resp["ok"]
        assert "d1" not in p._owner  # no ownership recorded
        assert all(p._load.get(id(s), 0) == 0 for s in FakeSidecar.instances)
        # some sidecar actually ran the replay
        assert any(
            o == ("replay", {"battle": "d1", "lines": lines})
            for s in FakeSidecar.instances
            for o in s.ops
        )

    _run(go())


def test_concurrent_replays_spread_across_pool():
    """A burst of in-flight replays must reserve transient load so they spread
    across sidecars instead of queueing on one process. PR#203 #3431925699."""
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        gate = asyncio.Event()

        async def blocking_replay(op, **kw):
            await gate.wait()
            return {"ok": True, "state": {"end": {"winner": "p1"}}}

        for s in p._sidecars:
            s.request = blocking_replay  # type: ignore[method-assign]

        # two replays launched while both are still otherwise idle
        t1 = asyncio.create_task(p.request("replay", battle="d1", lines=[]))
        t2 = asyncio.create_task(p.request("replay", battle="d2", lines=[]))
        for _ in range(4):  # let both route + reserve before they block on the gate
            await asyncio.sleep(0)

        # spread: each sidecar holds exactly one transient slot, not 2-on-1
        loads = sorted(p._load.get(id(s), 0) for s in p._sidecars)
        assert loads == [1, 1], f"replays should spread across the pool, got {loads}"
        assert p._owner == {}  # still ownerless

        gate.set()
        await asyncio.gather(t1, t2)
        # all transient load released after completion
        assert all(p._load.get(id(s), 0) == 0 for s in p._sidecars)
        assert p._owner == {}

    _run(go())


def test_replay_transient_load_released_on_error():
    """A replay that raises still releases its transient load slot."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        s = p._sidecars[0]

        async def boom(op, **kw):
            raise SidecarError("replay blew up")

        s.request = boom  # type: ignore[method-assign]
        with pytest.raises(SidecarError, match="blew up"):
            await p.request("replay", battle="d1", lines=[])
        assert p._load.get(id(s), 0) == 0  # released despite the error
        assert "d1" not in p._owner

    _run(go())


def test_replay_with_state_end_does_not_underflow_load():
    """A real replay response carries state.end; the release guard must pop
    nothing (replay was never owned) — no negative/leaked load."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        s = p._sidecars[0]

        async def replay_ending(op, **kw):
            return {"ok": True, "state": {"end": {"winner": "p1"}}}

        s.request = replay_ending  # type: ignore[method-assign]
        await p.request("replay", battle="d1", lines=[])
        assert p._load.get(id(s), 0) == 0
        assert "d1" not in p._owner

    _run(go())


def test_capacity_raises_when_pool_full():
    p = SidecarPool(size=1, max_battles_per_sidecar=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        with pytest.raises(SidecarError) as ei:
            await p.request("start", battle="b2")
        # "capacity" keyword → gateway maps to a retryable 503
        assert "capacity" in str(ei.value).lower()

    _run(go())


def test_restart_same_battle_is_idempotent():
    p = SidecarPool(size=1, max_battles_per_sidecar=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        await p.request("start", battle="b1")  # same battle again — no capacity error
        assert p._load[id(p._owner["b1"])] == 1

    _run(go())


def test_rss_mb_aggregates_across_pool():
    p = SidecarPool(size=3)
    _run(p.start())
    assert _run(p.rss_mb()) == pytest.approx(36.0)  # 3 × 12.0


def test_battleless_ops_round_robin():
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        await p.request("pack", team="...")
        await p.request("pack", team="...")

    _run(go())
    # both sidecars saw a pack op (round-robin)
    assert all(any(o[0] == "pack" for o in s.ops) for s in FakeSidecar.instances)


# ---- RECOVER-P1-sidecar-respawn: dead-member skip + touch-driven respawn ----


def test_least_loaded_skips_dead_sidecar():
    """A crashed member (returncode set) must never be assigned a new battle — its
    live count is 0 so it would otherwise look most-available (the corpse-routing
    bug RECOVER-P1-sidecar-respawn fixes)."""
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        dead, live = p._sidecars[0], p._sidecars[1]
        dead.returncode = 1  # simulate an OOM/crash
        await p.request("start", battle="b1")
        await p.request("start", battle="b2")
        # both battles landed on the LIVE sidecar, none on the corpse
        assert p._owner["b1"] is live and p._owner["b2"] is live
        assert p._load.get(id(dead), 0) == 0

    _run(go())


def test_reclaim_dead_respawns_and_evicts_routes():
    """A dead sidecar is replaced in place; its battle routes are evicted and the
    fresh member is live with zeroed load; capacity is restored."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        dead = p._owner["b1"]
        dead.returncode = 137  # OOM-killed

        assert await p.reclaim_dead() == ["b1"]  # the evicted battle_id is returned
        # b1's route is evicted (its state died with the process)
        assert "b1" not in p._owner
        # a fresh, live member sits in the slot; the corpse + its load are gone
        fresh = p._sidecars[0]
        assert fresh is not dead and fresh.returncode is None and fresh.started
        assert p._load[id(fresh)] == 0
        assert id(dead) not in p._load
        # capacity restored: a new battle routes to the fresh member
        await p.request("start", battle="b2")
        assert p._owner["b2"] is fresh

    _run(go())


def test_reclaim_dead_is_noop_when_all_alive():
    p = SidecarPool(size=2)
    _run(p.start())
    assert _run(p.reclaim_dead()) == []


def test_reclaim_dead_tears_down_a_failed_respawn(monkeypatch):
    """A respawn whose start() raises (e.g. Node ready-event timeout) spawns a child
    then raises without stopping it; reclaim_dead must tear that half-started process
    down, else every /healthz touch re-runs reclaim_dead and leaks another Node child
    (OOM spiral). PR #484 review (P1)."""
    p = SidecarPool(size=2)
    _run(p.start())
    p._sidecars[0].returncode = 1  # crash member 0 → reclaim_dead will respawn it

    stopped: list = []

    async def boom(self) -> None:  # the respawn's start() fails after "spawning"
        raise RuntimeError("node ready-event timeout")

    async def rec_stop(self) -> None:  # record that the failed respawn was torn down
        stopped.append(self)
        self.started = False

    monkeypatch.setattr(FakeSidecar, "start", boom)
    monkeypatch.setattr(FakeSidecar, "stop", rec_stop)

    # Best-effort: a failed respawn is reaped and skipped (NOT raised), so the
    # probe still reports the member dead (any_dead → 503) and retries next touch.
    assert _run(p.reclaim_dead()) == []

    # the half-started replacement was stopped (child reaped), not leaked
    assert len(stopped) == 1, "failed respawn was not torn down → leaks a Node child"
    # routing state untouched: the dead corpse is still in place, retried next touch
    assert p._sidecars[0].returncode == 1
    assert p.any_dead() is True  # still degraded → /healthz keeps 503ing


def test_reclaim_dead_evicts_routes_even_when_respawn_fails(monkeypatch):
    """A failed respawn must still evict the dead member's battle_ids. Otherwise
    reclaim_dead returns no IDs, the gateway leaves those sessions live, and
    /choose keeps routing into the dead pipe (opaque 400 instead of the intended
    409 'interrupted') until the container is recycled (PR #497 review
    PRRT_kwDOS0FXt86LqbQP). The dead slot itself stays so any_dead() keeps
    reporting and the next touch retries the respawn."""
    p = SidecarPool(size=1)
    _run(p.start())

    async def go() -> list[str]:
        await p.request("start", battle="b1")
        dead = p._owner["b1"]
        dead.returncode = 137  # OOM-killed

        # Force every subsequent start() to fail (the dead member's respawn
        # never wins). reclaim_dead must still surface "b1" so the gateway
        # can 409 it.
        async def boom(self) -> None:
            raise RuntimeError("node ready-event timeout")

        monkeypatch.setattr(FakeSidecar, "start", boom)
        return await p.reclaim_dead()

    evicted = _run(go())
    assert evicted == ["b1"], "respawn-failure path dropped the eviction"
    # The dead slot stays so /healthz keeps 503ing until the next retry succeeds.
    assert p.any_dead() is True
    # The owner row IS gone — /choose for b1 now 404s instead of routing into the
    # dead sidecar.
    assert "b1" not in p._owner


def test_reclaim_dead_evicts_before_failed_respawn_stop_can_be_cancelled(monkeypatch):
    """Evict the corpse-owned routes before awaiting failed-respawn cleanup.

    If the /healthz touch is cancelled while Sidecar.stop() waits on process exit,
    reclaim_dead may not return to the gateway, but the owner rows must already be
    gone so the next touch cannot leave live sessions pointing at the corpse.
    """
    p = SidecarPool(size=1)
    _run(p.start())

    async def go():
        await p.request("start", battle="b1")
        dead = p._owner["b1"]
        dead.returncode = 137

        stop_entered = asyncio.Event()
        stop_release = asyncio.Event()

        async def boom(self) -> None:
            self.started = True
            raise RuntimeError("node ready-event timeout")

        async def slow_stop(self) -> None:
            stop_entered.set()
            await stop_release.wait()
            self.started = False

        monkeypatch.setattr(FakeSidecar, "start", boom)
        monkeypatch.setattr(FakeSidecar, "stop", slow_stop)

        task = asyncio.create_task(p.reclaim_dead())
        await stop_entered.wait()
        task.cancel()
        stop_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert "b1" not in p._owner
        assert p.any_dead() is True
        assert await p.reclaim_dead() == ["b1"]
        assert p._pending_evictions == []

    _run(go())


def test_reclaim_dead_reaps_fresh_sidecar_when_cancelled_post_start():
    """When the caller is cancelled between fresh.start() succeeding and the
    swap landing, the replacement Node child must still be reaped — otherwise
    it is neither installed into self._sidecars nor stopped, and the dead slot
    retries the respawn next touch, leaking one Node child per cancellation
    (PR #497 review PRRT_kwDOS0FXt86LqbQH).

    The cancellation window is post-start, pre-swap: too tight to hit
    reliably with task.cancel() races. Deterministically inject the cancel by
    replacing self._lock with a gate that raises CancelledError on the SECOND
    acquire (the swap acquisition) — that is exactly the bug-window await.
    """
    p = SidecarPool(size=1)
    _run(p.start())
    dead = p._sidecars[0]
    dead.returncode = 137  # crashed → reclaim_dead will respawn

    class _CancelOnSecondAcquireLock:
        """asyncio.Lock that raises CancelledError when entered the Nth time."""

        def __init__(self, real: asyncio.Lock, raise_on_acquire: int) -> None:
            self._real = real
            self._raise_on = raise_on_acquire
            self.count = 0

        async def __aenter__(self):
            self.count += 1
            if self.count == self._raise_on:
                raise asyncio.CancelledError()
            return await self._real.__aenter__()

        async def __aexit__(self, *a):
            return await self._real.__aexit__(*a)

        def locked(self) -> bool:
            return self._real.locked()

    gated = _CancelOnSecondAcquireLock(p._lock, raise_on_acquire=2)
    p._lock = gated  # type: ignore[assignment]

    # Snapshot the pre-call sidecar list so we can identify `fresh` (the new
    # member spawned during reclaim_dead) versus the original `dead`.
    before = list(FakeSidecar.instances)
    with pytest.raises(asyncio.CancelledError):
        _run(p.reclaim_dead())
    after = list(FakeSidecar.instances)
    new_members = [s for s in after if s not in before]
    assert new_members, "expected reclaim_dead to spawn a fresh replacement"
    fresh = new_members[-1]

    # The cancellation reaped `fresh` (the slot's brand-new replacement) — not
    # the original corpse — so no Node child is leaked.
    assert fresh.started is False, (
        "post-start fresh sidecar was NOT stopped on cancellation — leaks a Node child"
    )
    # The dead corpse is still in place; the next touch retries the respawn.
    assert p._sidecars[0] is dead and p._sidecars[0].returncode == 137


def test_reclaim_dead_shields_post_start_stop_from_second_cancellation(monkeypatch):
    """A second cancellation while stop() drains must not interrupt fresh cleanup."""
    p = SidecarPool(size=1)
    _run(p.start())
    dead = p._sidecars[0]
    dead.returncode = 137

    class _CancelOnSecondAcquireLock:
        def __init__(self, real: asyncio.Lock, raise_on_acquire: int) -> None:
            self._real = real
            self._raise_on = raise_on_acquire
            self.count = 0

        async def __aenter__(self):
            self.count += 1
            if self.count == self._raise_on:
                raise asyncio.CancelledError()
            return await self._real.__aenter__()

        async def __aexit__(self, *a):
            return await self._real.__aexit__(*a)

        def locked(self) -> bool:
            return self._real.locked()

    p._lock = _CancelOnSecondAcquireLock(p._lock, raise_on_acquire=2)  # type: ignore[assignment]
    parent_task: asyncio.Task | None = None

    async def stop_with_second_cancel(self) -> None:
        assert parent_task is not None
        parent_task.cancel()
        await asyncio.sleep(0)
        self.started = False

    monkeypatch.setattr(FakeSidecar, "stop", stop_with_second_cancel)
    before = list(FakeSidecar.instances)

    async def go():
        nonlocal parent_task
        parent_task = asyncio.current_task()
        with pytest.raises(asyncio.CancelledError):
            await p.reclaim_dead()

    _run(go())
    new_members = [s for s in FakeSidecar.instances if s not in before]
    assert new_members, "expected reclaim_dead to spawn a fresh replacement"
    assert new_members[-1].started is False


def test_reclaim_does_not_hold_the_lock_while_starting_a_replacement(monkeypatch):
    """#2847: a slow Sidecar.start() must NOT block routing on healthy members —
    the pool lock has to be FREE while the replacement is starting, so one shard's
    multi-second respawn can't stall every live battle on the other shards."""
    p = SidecarPool(size=1)
    _run(p.start())
    p._sidecars[0].returncode = 137  # crash the member → reclaim will respawn it

    lock_free_observations: list[bool] = []
    orig_start = FakeSidecar.start

    async def slow_start(self) -> None:
        # Snapshot the lock the moment we're inside start() — it must be released.
        lock_free_observations.append(not p._lock.locked())
        await orig_start(self)

    monkeypatch.setattr(FakeSidecar, "start", slow_start)
    _run(p.reclaim_dead())
    assert lock_free_observations == [True], "pool lock was held across Sidecar.start()"


def test_concurrent_reclaim_does_not_double_swap(monkeypatch):
    """#2847: two concurrent reclaim touches on the same crashed member must swap it
    EXACTLY once — the slot re-check makes the loser reap its redundant fresh member
    instead of clobbering the winner's live replacement."""
    p = SidecarPool(size=1)
    _run(p.start())
    dead = p._sidecars[0]
    dead.returncode = 137

    gate = asyncio.Event()
    stopped: list = []
    stop_lock_free: list = []
    orig_stop = FakeSidecar.stop

    async def gated_start(self) -> None:
        await gate.wait()  # hold both racers inside start() until released
        self.started = True

    async def rec_stop(self) -> None:
        # #522 review P2: the redundant fresh member must be reaped OUTSIDE the pool
        # lock — Sidecar.stop() can block on graceful shutdown, and request() needs the
        # lock, so stopping under it stalls routing on every healthy member.
        stop_lock_free.append(not p._lock.locked())
        stopped.append(self)
        await orig_stop(self)

    monkeypatch.setattr(FakeSidecar, "start", gated_start)
    monkeypatch.setattr(FakeSidecar, "stop", rec_stop)

    async def go():
        t1 = asyncio.create_task(p.reclaim_dead())
        t2 = asyncio.create_task(p.reclaim_dead())
        await asyncio.sleep(0)  # let both reach `await gate.wait()` inside start()
        gate.set()
        await asyncio.gather(t1, t2)

    _run(go())
    # exactly one fresh member sits in the slot (alive); the corpse is gone
    assert p._sidecars[0] is not dead and p._sidecars[0].returncode is None
    assert p.size == 1 and not p.any_dead()
    # the redundant replacement (the loser's) was reaped, not leaked
    assert len(stopped) == 1, "slot re-check did not reap the redundant fresh member"
    assert stop_lock_free == [True], "redundant sidecar stopped while holding the pool lock"


def test_reclaim_dead_returns_all_evicted_battle_ids():
    """The gateway needs EVERY battle_id that died with a crashed member so it can
    fail each session closed (#2835), not just a count. Battles on surviving members
    are untouched."""
    p = SidecarPool(size=2)
    _run(p.start())

    async def go():
        await p.request("start", battle="a")
        await p.request("start", battle="b")
        victim = p._owner["a"]
        expected = {bid for bid, owner in p._owner.items() if owner is victim}
        survivors = {bid for bid, owner in p._owner.items() if owner is not victim}
        victim.returncode = 137  # OOM-kill the member that owns "a"

        evicted = await p.reclaim_dead()

        assert set(evicted) == expected  # exactly the dead member's battle_ids
        assert all(bid not in p._owner for bid in expected)  # their routes are gone
        assert all(bid in p._owner for bid in survivors)  # the rest keep routing

    _run(go())
