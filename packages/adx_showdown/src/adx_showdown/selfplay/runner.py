"""A1 — the self-play battle runner (SPEC Lane A1 / Contract 2, ADR-0014).

Realizes a :class:`~adx_showdown.harness.BattleHarness` as a live poke-env
``Player`` and runs it against an opponent (another harness for true self-play,
or a held-out baseline for honest scoring), producing the **Contract-2
``BattleResult``** that A3's ``multi_dim_fitness`` consumes and that the C2
e2e-driver's ``_mock_run_vs_baselines`` seam is replaced with.

Substrate reconciliation (SPEC said "over adx_showdown sim"): A3 already shipped
its held-out baselines as **poke-env Players** (``baselines.build_baseline`` →
``poke_env.Player`` against a live PS server), and the ADR-0014 substrate + the
Phase-1 spikes are poke-env. So A1 runs on **poke-env vs the PS server** for
cross-lane coherence — a harness-vs-poke-env-baseline battle is only possible on
one shared engine. Exact ``(seed, inputLog)`` byte-determinism is the ADR-0014
§5 open item; the DONE criterion scores over N battles with a CI, so the runner
is reproducible-in-distribution (seeded usernames + the random strategy's RNG).

poke-env is imported lazily (the fitness/genome path stays poke-env-free); the
Contract-2 result type + the pure aggregation are import-safe without it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.harness import BattleHarness, from_bene_genome
from adx_showdown.selfplay.baselines import (
    baseline_names,
    build_baseline,
    max_base_power_choice,
)

DEFAULT_FORMAT = "gen9randombattle"
_PS_HOST = os.environ.get("ADX_PS_HOST", "127.0.0.1")
_PS_PORT = os.environ.get("ADX_PS_PORT", "8000")
# Where per-matchup traces are written (battle outcomes for replay/audit).
_TRACE_DIR = Path(os.environ.get("ADX_SELFPLAY_TRACE_DIR", "/tmp/selfplay"))

# Bounded thread pool for the LIVE codex move hook. The codex CLI is a blocking
# subprocess; running it inline in the async battle loop would stall the event
# loop (and every other MCP/arena request) for up to the per-move timeout. We run
# it off-loop here and CAP concurrency (``ADX_CODEX_MAX_CONCURRENCY``, default 4)
# so a fan-out of concurrent battles can't spawn an unbounded pile of codex procs.
# Lazily created so the default (greedy / non-live) path never builds a pool.
_codex_executor: ThreadPoolExecutor | None = None


def _get_codex_executor() -> ThreadPoolExecutor:
    global _codex_executor
    if _codex_executor is None:
        try:
            max_workers = max(1, int(os.environ.get("ADX_CODEX_MAX_CONCURRENCY", "4") or "4"))
        except (TypeError, ValueError):
            max_workers = 4  # mistyped override must not crash a battle — fail safe
        _codex_executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="adx-codex"
        )
    return _codex_executor


class SelfPlayResult(BaseModel):
    """Contract-2 ``BattleResult`` (named ``SelfPlayResult`` to avoid shadowing
    :class:`adx_showdown.sim.BattleResult`). ``model_dump()`` is the exact dict
    A3's ``multi_dim_fitness`` reads."""

    model_config = ConfigDict(extra="forbid")

    winner: str  # "a" | "b" | "draw"  (side-a is the candidate harness)
    battles: list[dict[str, Any]] = Field(default_factory=list)
    trace_path: str = ""
    raw_dims: dict[str, Any] = Field(default_factory=dict)


def _short_user(*parts: Any) -> str:
    """A unique, PS-legal (<=18 char) username for a player instance."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=6).hexdigest()
    return f"adx{h}"  # 3 + 12 = 15 chars


def _seeded_index(modulo: int, *parts: Any) -> int:
    """A deterministic index in ``[0, modulo)`` from ``parts`` via a stable hash
    (blake2b — NOT the PYTHONHASHSEED-salted builtin ``hash``), so a ``random``
    policy is reproducible across processes from the same ``rng_seed``."""
    digest = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % modulo


def _filter_switch_orders(orders: list[Any], *, exclude_switches: bool) -> list[Any]:
    """Drop voluntary switch orders from a poke-env ``valid_orders`` list when the
    genome forbids switching. A switch order's Showdown message is ``/choose switch
    <name>`` (a move is ``/choose move <id>``, so a move named e.g. Switcheroo is NOT
    matched). When exclusion is requested, switches are removed unconditionally — even
    if that leaves an empty list: the caller only excludes on a VOLUNTARY (non-forced)
    turn, so "every order is a switch" must NOT be treated as a forced switch and
    restored (forced switches are routed by the caller via ``force_switch``). The
    empty case is handled by ``_seeded_order``'s last-resort ``choose_random_move``."""
    if not exclude_switches:
        return orders
    return [o for o in orders if not str(getattr(o, "message", "")).startswith("/choose switch")]


def _resolve_codex_decide() -> Any:
    """The live-codex ``DecideFn`` when ``ADX_CODEX_LIVE=1`` (codex picks each move via
    the real CLI, driven by the harness prompt), else ``None`` → the adapter's
    deterministic greedy default. Lazy import keeps the subprocess/codex module out of
    the default + test + poke-env-free path."""
    if os.environ.get("ADX_CODEX_LIVE") != "1":
        return None
    from adx_showdown.selfplay.codex_decide import codex_decide

    return codex_decide


def _server_config(host: str | None = None, port: str | None = None) -> Any:
    from poke_env import ServerConfiguration

    return ServerConfiguration(
        f"ws://{host or _PS_HOST}:{port or _PS_PORT}/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )


def make_harness_player(
    harness: BattleHarness | dict[str, Any],
    *,
    rng_seed: int = 0,
    account: Any = None,
    server: Any = None,
    battle_format: str = DEFAULT_FORMAT,
) -> Any:
    """Build the live poke-env ``Player`` for a harness (lazy poke-env import).

    Strategy realization: ``random`` picks a uniformly-random legal order and
    ``max_damage`` == the ``MaxBasePowerPlayer`` decision seam, so a
    baseline-as-harness reproduces the baseline. Other known strategies fall back
    to max_damage for now (richer fidelity + ``llm_freeform`` codex deferral are
    follow-ups); ``total_moves`` / ``illegal_moves`` are tracked for raw_dims.

    ``rng_seed`` makes the ``random`` policy reproducible: every random choice is
    drawn deterministically from ``(rng_seed, turn, the legal-order set)`` instead
    of poke-env's unseeded ``choose_random_move``, so the same decision context
    always yields the same move. Keying on the legal options themselves (not the
    server-assigned ``battle_tag``) keeps it stable across runs + independent of
    call order across the player's concurrent battles.
    """
    from poke_env.player import Player

    h = from_bene_genome(harness)

    class HarnessPlayer(Player):
        strategy = h.move_selection_strategy

        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.total_moves = 0
            self.illegal_moves = 0

        def _note_illegal(self) -> None:
            """Record that the codex/LLM policy proposed an id outside the legal
            moves. Plumbed into ``raw_dims["illegal_moves"]`` → A3's
            ``move_legibility``, so a policy that hallucinates illegal moves is
            penalized instead of scoring a free perfect legibility (the seam still
            substitutes a legal move, so the battle is unaffected)."""
            self.illegal_moves += 1

        def _seeded_order(self, battle: Any, *, exclude_switches: bool = False) -> Any:
            """A reproducible random legal choice, replacing poke-env's unseeded
            ``choose_random_move``. Draws from poke-env's FULL legal order set
            (``battle.valid_orders`` — moves incl. tera / dynamax / mega / Z +
            switches, not just ``available_moves`` + ``available_switches``) and
            keys the pick on ``rng_seed`` + the turn + the legal options' stable
            Showdown command strings (NOT the server-assigned ``battle_tag``), so
            an identical decision context yields the same choice regardless of run
            or call order across concurrent battles. ``exclude_switches`` drops
            voluntary switch orders so a codex-abstention fallback honors the genome's
            ``allow_switch`` instead of sneaking a switch back in."""
            orders = _filter_switch_orders(
                list(getattr(battle, "valid_orders", None) or []), exclude_switches=exclude_switches
            )
            if not orders:
                # Nothing legal survived. If we deliberately EXCLUDED switches (a
                # voluntary, non-forced no-move turn under allow_switch=false) and
                # only switches were legal, do NOT re-sample valid_orders via
                # ``choose_random_move`` — that reintroduces the very switch the policy
                # forbids. Defer to showdown's own default ("/choose default") so OUR
                # code never picks a policy-forbidden switch. The non-excluding paths
                # (random / max_damage forced switch) keep the seeded random fallback.
                return (
                    self.choose_default_move()
                    if exclude_switches
                    else self.choose_random_move(battle)
                )
            key = "|".join(str(o) for o in orders)
            idx = _seeded_index(len(orders), rng_seed, getattr(battle, "turn", 0), key)
            return orders[idx]

        async def choose_move(self, battle: Any) -> Any:
            # poke-env awaits ``choose_move`` when it returns a coroutine, so this
            # is async ONLY to keep the live-codex subprocess off the event loop
            # (below); the synchronous strategies just return inline.
            self.total_moves += 1
            moves = list(getattr(battle, "available_moves", None) or [])
            if self.strategy == "random":
                return self._seeded_order(battle)
            # codex move seam (Contract 5): llm_freeform / codex strategies route
            # each turn's decision to the C1 adapter, so codex drives moves
            # through the selfplay_battle MCP tool (SPEC DONE #1). Routed even on a
            # FORCED switch (no moves, only switches) so the harness policy — not the
            # seeded random fallback — picks the switch; the adapter returns None only
            # when nothing is legal. Lazy import keeps the non-codex path + poke-env-
            # free callers untouched.
            if self.strategy in ("llm_freeform", "codex"):
                from adx_showdown.selfplay.codex_adapter import select_codex_move

                decide = _resolve_codex_decide()
                if decide is None:
                    # greedy default — pure + fast, no subprocess; stays on-loop.
                    chosen = select_codex_move(h, battle, on_illegal=self._note_illegal)
                else:
                    # LIVE codex: the decide hook shells out to the blocking codex
                    # CLI. Run it OFF the event loop in the bounded codex pool so a
                    # slow call can't stall other MCP/arena requests. Surface an
                    # illegal proposal back on the event-loop thread (not the worker)
                    # so the counter stays race-free across concurrent battles.
                    flagged: list[bool] = []
                    loop = asyncio.get_running_loop()
                    chosen = await loop.run_in_executor(
                        _get_codex_executor(),
                        lambda: select_codex_move(
                            h, battle, decide=decide, on_illegal=lambda: flagged.append(True)
                        ),
                    )
                    if flagged:
                        self._note_illegal()
                if chosen is not None:
                    return self.create_order(chosen)
                # abstention / failure: fall back to a seeded legal order, but keep
                # the genome's allow_switch — a voluntary switch must not sneak in via
                # the fallback (a forced switch still must). The seeded order otherwise
                # samples valid_orders, which includes switches.
                allow_switch = bool(getattr(getattr(h, "tool_policy", None), "allow_switch", True))
                force_switch = bool(getattr(battle, "force_switch", False))
                return self._seeded_order(
                    battle, exclude_switches=(not force_switch and not allow_switch)
                )
            # non-codex strategies with no legal move (e.g. a forced switch) defer to
            # the seeded random legal order.
            if not moves:
                return self._seeded_order(battle)
            # max_damage and every other (non-llm) strategy: highest base power.
            best = max_base_power_choice(moves)
            if best is None:
                return self._seeded_order(battle)
            return self.create_order(best)

    return HarnessPlayer(
        account_configuration=account,
        server_configuration=server or _server_config(),
        battle_format=battle_format,
    )


def _aggregate(
    *,
    wins_a: int,
    wins_b: int,
    draws: int,
    n_battles: int,
    total_turns: int,
    total_moves: int,
    illegal_moves: int,
    forfeits: int,
    opponent_baseline: str,
) -> tuple[str, dict[str, Any]]:
    """Pure: fold per-matchup counts into (winner, Contract-2 raw_dims).

    Kept side-effect-free so it is unit-testable without a PS server."""
    if wins_a > wins_b:
        winner = "a"
    elif wins_b > wins_a:
        winner = "b"
    else:
        winner = "draw"
    raw_dims = {
        "opponent_baseline": opponent_baseline,
        "n_battles": n_battles,
        "wins_a": wins_a,
        "draws": draws,
        "turns": total_turns,
        "forfeits": forfeits,
        "illegal_moves": illegal_moves,
        "total_moves": total_moves,
    }
    return winner, raw_dims


def _write_trace(tag: str, battles: list[dict[str, Any]]) -> str:
    try:
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)
        path = _TRACE_DIR / f"{tag}.json"
        path.write_text(json.dumps({"tag": tag, "battles": battles}, indent=2))
        return str(path)
    except OSError:
        return ""  # trace is best-effort; never fail a battle on disk issues


async def _run_matchup(
    player_a: Any,
    player_b: Any,
    *,
    n_battles: int,
    opponent_baseline: str,
    trace_tag: str,
) -> SelfPlayResult:
    """Run ``n_battles`` of player_a (candidate) vs player_b; fold into Contract-2.

    Closes both players' websockets in a ``finally`` so connections do NOT
    accumulate across the many matchups of an evolution run — left open, a local
    ``--no-security`` PS server starts rejecting logins ("Expected <user> to be
    logged in") once enough sockets pile up. Cleanup is best-effort."""
    try:
        await player_a.battle_against(player_b, n_battles=n_battles)

        battles: list[dict[str, Any]] = []
        total_turns = 0
        for tag, battle in player_a.battles.items():
            turn = int(getattr(battle, "turn", 0) or 0)
            total_turns += turn
            won = getattr(battle, "won", None)
            battles.append({"tag": tag, "won_a": won, "turns": turn})

        wins_a = player_a.n_won_battles
        wins_b = player_a.n_lost_battles
        draws = player_a.n_tied_battles
        winner, raw_dims = _aggregate(
            wins_a=wins_a,
            wins_b=wins_b,
            draws=draws,
            n_battles=n_battles,
            total_turns=total_turns,
            total_moves=int(getattr(player_a, "total_moves", 0)),
            illegal_moves=int(getattr(player_a, "illegal_moves", 0)),
            forfeits=0,  # HarnessPlayers never forfeit; codex/llm path refines this
            opponent_baseline=opponent_baseline,
        )
        return SelfPlayResult(
            winner=winner,
            battles=battles,
            trace_path=_write_trace(trace_tag, battles),
            raw_dims=raw_dims,
        )
    finally:
        for p in (player_a, player_b):
            try:
                await p.ps_client.stop_listening()
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass


async def run_selfplay_battle(
    harness_a: BattleHarness | dict[str, Any],
    harness_b: BattleHarness | dict[str, Any],
    *,
    seed: int,
    n_battles: int,
    opponent_baseline: str | None = None,
    battle_format: str = DEFAULT_FORMAT,
    server: Any = None,
) -> SelfPlayResult:
    """Contract 2: run ``harness_a`` (candidate) vs ``harness_b`` over n_battles.

    Both harnesses are realized as poke-env ``HarnessPlayer``s on the PS server.
    ``opponent_baseline`` labels harness_b for A3's Elo lookup (defaults to
    harness_b's id). Reproducible-in-distribution via seeded usernames.
    """
    a = from_bene_genome(harness_a)
    b = from_bene_genome(harness_b)
    from poke_env import AccountConfiguration

    server = server or _server_config()
    pa = make_harness_player(
        a,
        rng_seed=seed,
        account=AccountConfiguration(_short_user(a.harness_id, "a", seed), None),
        server=server,
        battle_format=battle_format,
    )
    pb = make_harness_player(
        b,
        rng_seed=seed + 1,
        account=AccountConfiguration(_short_user(b.harness_id, "b", seed), None),
        server=server,
        battle_format=battle_format,
    )
    return await _run_matchup(
        pa,
        pb,
        n_battles=n_battles,
        opponent_baseline=opponent_baseline or b.harness_id,
        trace_tag=_short_user(a.harness_id, b.harness_id, seed),
    )


async def run_vs_baselines(
    harness: BattleHarness | dict[str, Any],
    run_seed: int,
    n_battles: int,
    *,
    battle_format: str = DEFAULT_FORMAT,
    server: Any = None,
) -> list[dict[str, Any]]:
    """Held-out eval — run ``harness`` vs EVERY held-out baseline, one Contract-2
    result per matchup. Replaces the C2 driver's ``_mock_run_vs_baselines`` seam.

    Returns ``model_dump()`` dicts (what the fitness fn + driver consume).
    """
    from poke_env import AccountConfiguration

    h = from_bene_genome(harness)
    server = server or _server_config()
    results: list[dict[str, Any]] = []
    for i, name in enumerate(baseline_names()):
        cand = make_harness_player(
            h,
            rng_seed=run_seed + i,
            account=AccountConfiguration(_short_user(h.harness_id, name, run_seed), None),
            server=server,
            battle_format=battle_format,
        )
        opp = build_baseline(
            name,
            account_configuration=AccountConfiguration(
                _short_user(name, h.harness_id, run_seed), None
            ),
            server_configuration=server,
            battle_format=battle_format,
        )
        res = await _run_matchup(
            cand,
            opp,
            n_battles=n_battles,
            opponent_baseline=name,
            trace_tag=_short_user(h.harness_id, name, run_seed),
        )
        results.append(res.model_dump())
    return results
