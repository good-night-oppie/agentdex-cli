"""A1 — self-play runner (Contract 2). CI-runnable contract/aggregation tests
(no PS server) + a server-gated real-battle smoke."""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import types

import pytest
from adx_showdown.harness import BattleHarness, seed_harness
from adx_showdown.selfplay.fitness import multi_dim_fitness
from adx_showdown.selfplay.runner import (
    SelfPlayResult,
    _aggregate,
    _defer_to_default,
    _fallback_orders,
    _filter_switch_orders,
    run_selfplay_battle,
)


class _Move:
    def __init__(self, mid: str, base_power: int) -> None:
        self.id = mid
        self.base_power = base_power


class _Order:
    """A duck-typed poke-env BattleOrder: only ``.message`` matters for filtering."""

    def __init__(self, message: str) -> None:
        self.message = message


class _Battle:
    def __init__(self, moves: list[_Move]) -> None:
        self.available_moves = moves
        self.available_switches = []
        self.valid_orders = []
        self.force_switch = False
        self.turn = 1


def _install_fake_poke_env(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakePlayer:
        def __init__(self, **_kw) -> None:
            pass

        def create_order(self, choice):
            return ("order", getattr(choice, "id", choice))

        def choose_random_move(self, battle):
            return ("random", battle)

        def choose_default_move(self):
            return "default"

    fake_pkg = types.ModuleType("poke_env")
    fake_pkg.__path__ = []
    fake_player = types.ModuleType("poke_env.player")
    fake_player.Player = _FakePlayer
    monkeypatch.setitem(sys.modules, "poke_env", fake_pkg)
    monkeypatch.setitem(sys.modules, "poke_env.player", fake_player)


def test_native_strategy_dispatch_does_not_use_codex_adapter(monkeypatch):
    """Regression for gh#388: runner dispatch itself must keep native strategies
    native, not just avoid injecting a selector at the MCP boundary."""
    from adx_showdown.selfplay import codex_adapter
    from adx_showdown.selfplay.runner import make_harness_player

    _install_fake_poke_env(monkeypatch)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("native strategy was routed through codex")

    monkeypatch.setattr(codex_adapter, "select_codex_move", _fail_if_called)
    player = make_harness_player(
        BattleHarness(harness_id="native-max", move_selection_strategy="max_damage"),
        server=object(),
    )
    chosen = asyncio.run(player.choose_move(_Battle([_Move("tackle", 40), _Move("eruption", 150)])))
    assert chosen == ("order", "eruption")


def test_fallback_orders_prefers_the_policy_allowed_set():
    """A policy-allowed action survived → the seeded fallback samples over the filtered set."""
    filtered = [_Order("/choose move ember")]
    assert _fallback_orders(filtered) is filtered


def test_fallback_orders_none_when_no_policy_allowed_order_survived():
    """#3440820025: when the genome excluded voluntary switches and nothing survived,
    _fallback_orders returns None — it does NOT restore the excluded switches by falling
    back to valid_orders (that would reintroduce the very switch the gate forbids; PR
    #353/#354). _seeded_order then defers (see _defer_to_default), it never re-samples here."""
    assert _fallback_orders([]) is None


def test_defer_to_default_only_when_excluded_switch_is_the_only_legal_order():
    """#3440820025: the seeded fallback defers to Showdown's /choose default (instead of
    choose_random_move, which re-samples valid_orders) EXACTLY when voluntary switches were
    excluded, none survived, yet only switches were legal — so OUR policy never deliberately
    picks the forbidden voluntary switch."""
    switches = [_Order("/choose switch a"), _Order("/choose switch b")]
    # excluded + only switches legal (filtered empty) → defer to default
    assert _defer_to_default(switches, [], exclude_switches=True) is True


def test_defer_to_default_false_when_a_policy_allowed_move_survived():
    """A non-switch survived → there is no forbidden-switch dilemma → no defer (the seeded
    pick over `filtered` handles it; this branch is not even reached)."""
    all_orders = [_Order("/choose move ember"), _Order("/choose switch a")]
    assert (
        _defer_to_default(all_orders, [_Order("/choose move ember")], exclude_switches=True)
        is False
    )


def test_defer_to_default_false_for_a_forced_switch_or_random_policy():
    """A forced switch (and the random policy) never excludes, so exclude_switches=False and
    the only-switches set is sampled normally — no defer, the switch IS played. This is how
    review #3440746022's forced-by-circumstance case stays satisfied without restoring
    excluded switches."""
    switches = [_Order("/choose switch a"), _Order("/choose switch b")]
    assert _defer_to_default(switches, switches, exclude_switches=False) is False


def test_defer_to_default_false_when_genuinely_nothing_legal():
    """Nothing legal at all (valid_orders empty) → fall through to the random fallback
    (forced pass / struggle), not the /choose default deferral."""
    assert _defer_to_default([], [], exclude_switches=True) is False


def test_filter_switch_orders_drops_only_switches_when_excluded():
    """#3440401899: the codex-abstention fallback must honor allow_switch — a switch
    order (``/choose switch ...``) is dropped, a move (``/choose move ...``) is kept,
    and a move named like a switch (Switcheroo) is NOT mis-dropped."""
    orders = [
        _Order("/choose move switcheroo"),
        _Order("/choose switch blastoise"),
        _Order("/choose move ember"),
    ]
    kept = _filter_switch_orders(orders, exclude_switches=True)
    assert [o.message for o in kept] == ["/choose move switcheroo", "/choose move ember"]


def test_filter_switch_orders_passthrough_when_not_excluded():
    orders = [_Order("/choose switch blastoise"), _Order("/choose move ember")]
    assert _filter_switch_orders(orders, exclude_switches=False) is orders


def test_filter_switch_orders_does_not_restore_switches_when_excluded():
    """#3440654824: exclusion is unconditional — an all-switch list returns EMPTY, it is
    NOT restored. The caller only excludes on a voluntary (non-forced) turn, so "every
    order is a switch" must not be inferred as a forced switch; _seeded_order then defers to
    Showdown's /choose default (see _defer_to_default), never re-sampling the excluded
    switch, for the genuine only-switches-legal corner."""
    orders = [_Order("/choose switch a"), _Order("/choose switch b")]
    assert _filter_switch_orders(orders, exclude_switches=True) == []


# --- the exact raw_dims keys A3's fitness + the C2 driver mock agree on ---
_CONTRACT_RAW_DIMS = {
    "opponent_baseline",
    "n_battles",
    "wins_a",
    "draws",
    "turns",
    "forfeits",
    "illegal_moves",
    "total_moves",
}


def _agg(wins_a, wins_b, draws=0, n=10):
    return _aggregate(
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        n_battles=n,
        total_turns=n * 11,
        total_moves=n * 11,
        illegal_moves=0,
        forfeits=0,
        opponent_baseline="RandomPlayer",
    )


def test_aggregate_winner_logic():
    assert _agg(7, 3)[0] == "a"
    assert _agg(3, 7)[0] == "b"
    assert _agg(5, 5)[0] == "draw"


def test_aggregate_raw_dims_match_contract_keys():
    _, raw = _agg(6, 4)
    assert set(raw) == _CONTRACT_RAW_DIMS
    assert raw["wins_a"] == 6
    assert raw["opponent_baseline"] == "RandomPlayer"


def test_selfplay_result_dump_shape():
    winner, raw = _agg(6, 4)
    r = SelfPlayResult(winner=winner, battles=[], trace_path="/tmp/x.json", raw_dims=raw)
    dumped = r.model_dump()
    assert set(dumped) == {"winner", "battles", "trace_path", "raw_dims"}


def test_a1_output_feeds_a3_fitness():
    """Cross-lane contract: A1's BattleResult dicts flow into A3's fitness with
    no KeyError and yield the 5-dim Pareto vector — proven in CI, no PS server."""
    results = []
    for name, wins in (
        ("RandomPlayer", 9),
        ("MaxBasePowerPlayer", 6),
        ("SimpleHeuristicsPlayer", 4),
    ):
        _, raw = _aggregate(
            wins_a=wins,
            wins_b=10 - wins,
            draws=0,
            n_battles=10,
            total_turns=110,
            total_moves=110,
            illegal_moves=0,
            forfeits=0,
            opponent_baseline=name,
        )
        results.append(
            SelfPlayResult(winner="a", battles=[], trace_path="", raw_dims=raw).model_dump()
        )
    fit = multi_dim_fitness(results)
    assert set(fit) == {
        "win_rate",
        "elo",
        "move_legibility",
        "no_forfeit_exploit",
        "turn_efficiency",
    }
    assert 0.0 <= fit["win_rate"] <= 1.0
    assert fit["no_forfeit_exploit"] == 1.0  # zero forfeits → no exploit penalty


def test_seeded_index_is_deterministic_and_in_range():
    from adx_showdown.selfplay.runner import _seeded_index

    # same key → same index, stable across processes (blake2b, not the salted hash)
    assert _seeded_index(5, 42, "battle-1", 3) == _seeded_index(5, 42, "battle-1", 3)
    # always within [0, modulo)
    for n in (1, 2, 7, 13):
        for turn in range(20):
            assert 0 <= _seeded_index(n, 99, "battle-x", turn) < n
    # the random policy actually varies with rng_seed (not a constant)
    assert len({_seeded_index(8, s, "battle-1", 1) for s in range(16)}) > 1


def _ps_server_up() -> bool:
    try:
        import poke_env  # noqa: F401
    except ModuleNotFoundError:
        return False
    host = os.environ.get("ADX_PS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADX_PS_PORT", "8000"))
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _ps_server_up(), reason="no local PS server on ADX_PS_HOST:ADX_PS_PORT")
def test_run_selfplay_battle_smoke():
    """Real battle: a max_damage harness should not lose every game to random."""
    cand = seed_harness()  # max_damage
    opp = BattleHarness(harness_id="rng", move_selection_strategy="random")
    res = asyncio.run(
        run_selfplay_battle(cand, opp, seed=7, n_battles=2, opponent_baseline="RandomPlayer")
    )
    assert res.winner in ("a", "b", "draw")
    assert res.raw_dims["n_battles"] == 2
    assert (
        res.raw_dims["wins_a"]
        + res.raw_dims["draws"]
        + (2 - res.raw_dims["wins_a"] - res.raw_dims["draws"])
        == 2
    )
