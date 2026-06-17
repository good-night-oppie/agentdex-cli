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
