"""PvP matchmaking + choice routing unit tests (GA-ARENA-MODES).

No sidecar, no gateway — pure asyncio.
"""

from __future__ import annotations

import asyncio

import pytest
from adx_showdown.pvp import PvPChoiceRouter, PvPPairing, PvPQueue

# ── PvPQueue ─────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


async def _pair_two(a: str = "alice", b: str = "bob"):
    q = PvPQueue()
    fut_a = asyncio.ensure_future(q.enqueue(a))
    await asyncio.sleep(0)  # yield so fut_a suspends in queue
    pairing_b = await q.enqueue(b)
    pairing_a = await fut_a
    return pairing_a, pairing_b


def test_pvp_queue_pairs_two_owners():
    pa, pb = _run(_pair_two())
    assert pa.role == "p1"
    assert pb.role == "p2"
    assert pa.battle_id == pb.battle_id
    assert pa.opponent_owner == "bob"
    assert pb.opponent_owner == "alice"


def test_pvp_queue_battle_id_prefixed():
    pa, _ = _run(_pair_two())
    assert pa.battle_id.startswith("pvp-")


def test_pvp_queue_fifo_ordering():
    # The first owner to queue gets role p1; they are paired with the NEXT
    # joiner.  A second round re-confirms ordering with a fresh pair.
    async def _rounds():
        q = PvPQueue()
        # Round 1: "a" waits, "b" pairs immediately with a
        fut_a = asyncio.ensure_future(q.enqueue("a"))
        await asyncio.sleep(0)
        pb = await q.enqueue("b")  # b is 2nd → p2
        pa = await fut_a  # a was 1st → p1
        assert pa.role == "p1" and pb.role == "p2"
        assert pa.opponent_owner == "b" and pb.opponent_owner == "a"
        assert pa.battle_id == pb.battle_id
        # Round 2: independent queue, c waits, d pairs
        fut_c = asyncio.ensure_future(q.enqueue("c"))
        await asyncio.sleep(0)
        pd = await q.enqueue("d")
        pc = await fut_c
        assert pc.role == "p1" and pd.role == "p2"
        assert pc.battle_id != pa.battle_id  # distinct battles

    _run(_rounds())


def test_pvp_queue_duplicate_enqueue_raises():
    async def _dup():
        q = PvPQueue()
        asyncio.ensure_future(q.enqueue("alice"))
        await asyncio.sleep(0)
        with pytest.raises(ValueError, match="already in the PvP queue"):
            await q.enqueue("alice")

    _run(_dup())


def test_pvp_queue_cancel_removes_waiter():
    async def _cancel():
        q = PvPQueue()
        asyncio.ensure_future(q.enqueue("alice"))
        await asyncio.sleep(0)
        assert q.queue_depth == 1
        q.cancel("alice")
        assert q.queue_depth == 0
        # bob can now queue without seeing alice
        asyncio.ensure_future(q.enqueue("bob"))
        await asyncio.sleep(0)
        carol = await q.enqueue("carol")
        assert carol.opponent_owner == "bob"

    _run(_cancel())


def test_pvp_queue_depth():
    # queue_depth counts owners currently WAITING (i.e. who arrived first and
    # have no match yet).  The second joiner always pairs immediately → depth
    # never exceeds 1 in normal two-at-a-time flow.
    async def _depth():
        q = PvPQueue()
        assert q.queue_depth == 0
        fut_a = asyncio.ensure_future(q.enqueue("a"))
        await asyncio.sleep(0)
        assert q.queue_depth == 1  # a is waiting
        # b arrives → pairs with a immediately, depth back to 0
        _ = await q.enqueue("b")
        await fut_a  # collect a's result to avoid "never retrieved" warning
        assert q.queue_depth == 0
        # c waits again
        asyncio.ensure_future(q.enqueue("c"))
        await asyncio.sleep(0)
        assert q.queue_depth == 1

    _run(_depth())


def test_pvp_pairing_frozen():
    p = PvPPairing(battle_id="pvp-abc", role="p1", opponent_owner="bob")
    with pytest.raises(Exception):
        p.role = "p2"  # type: ignore[misc]


# ── PvPChoiceRouter ───────────────────────────────────────────────────────────


def test_pvp_choice_router_buffered_before_policy():
    async def _buf():
        router = PvPChoiceRouter()
        policy = router.make_p2_policy("b1")
        # P2 submits before _advance calls the policy
        router.submit_p2_choice("b1", "move 1")
        # policy call returns immediately with buffered value
        result = await policy(None)
        assert result == "move 1"

    _run(_buf())


def test_pvp_choice_router_await_then_submit():
    async def _live():
        router = PvPChoiceRouter()
        policy = router.make_p2_policy("b2")
        fut = asyncio.ensure_future(policy(None))
        await asyncio.sleep(0)
        assert router.is_waiting_for_p2("b2")
        accepted = router.submit_p2_choice("b2", "switch 2")
        assert accepted is True
        result = await fut
        assert result == "switch 2"

    _run(_live())


def test_pvp_choice_router_submit_buffered_when_not_waiting():
    router = PvPChoiceRouter()
    accepted = router.submit_p2_choice("b3", "move 3")
    assert accepted is False  # buffered, not live-accepted
    assert not router.is_waiting_for_p2("b3")


def test_pvp_choice_router_cleanup():
    async def _clean():
        router = PvPChoiceRouter()
        policy = router.make_p2_policy("b4")
        asyncio.ensure_future(policy(None))
        await asyncio.sleep(0)
        assert router.is_waiting_for_p2("b4")
        router.cleanup("b4")
        assert not router.is_waiting_for_p2("b4")

    _run(_clean())
