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

        assert await p.reclaim_dead() == 1
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
    assert _run(p.reclaim_dead()) == 0
