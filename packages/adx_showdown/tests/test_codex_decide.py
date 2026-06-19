"""L1 — the live codex move hook. Unit-tested with an INJECTED fake codex runner so
CI never shells out; a real codex CLI is exercised only by the gated live smoke."""

from __future__ import annotations

from adx_showdown.selfplay.codex_adapter import codex_context, select_codex_move
from adx_showdown.selfplay.codex_decide import _build_prompt, _parse_last_json, codex_decide


class _Move:
    def __init__(self, mid: str, base_power: int) -> None:
        self.id = mid
        self.base_power = base_power


class _Battle:
    def __init__(self, moves: list[_Move]) -> None:
        self.available_moves = moves
        self.active_pokemon = None
        self.force_switch = False


class _Harness:
    system_prompt = "Prefer super-effective coverage; never stall."
    params: dict = {}


def _ctx(moves: list[_Move]) -> dict:
    return codex_context(_Battle(moves))


def test_codex_decide_returns_the_chosen_legal_move():
    ctx = _ctx([_Move("thunderbolt", 90), _Move("tackle", 40)])
    out = codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "thunderbolt"})
    assert out == "thunderbolt"


def test_codex_decide_rejects_an_illegal_pick():
    ctx = _ctx([_Move("thunderbolt", 90)])
    assert codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "hyperbeam"}) is None


def test_codex_decide_is_failsafe_on_error():
    ctx = _ctx([_Move("thunderbolt", 90)])

    def boom(p, s, t):
        raise TimeoutError("codex hung")

    assert codex_decide(_Harness(), ctx, run=boom) is None


def test_codex_decide_no_legal_moves_returns_none():
    assert codex_decide(_Harness(), _ctx([]), run=lambda p, s, t: {"move_id": "x"}) is None


def test_prompt_embeds_the_evolving_policy_and_legal_ids():
    ctx = _ctx([_Move("surf", 90), _Move("tackle", 40)])
    prompt = _build_prompt(_Harness(), ctx, ["surf", "tackle"])
    assert "Prefer super-effective coverage" in prompt  # the harness policy p drives the choice
    assert "surf" in prompt and "tackle" in prompt


def test_parse_last_json_takes_the_last_block():
    assert _parse_last_json('noise {"a": 1} more {"move_id": "surf"}') == {"move_id": "surf"}


def test_end_to_end_through_select_codex_move():
    # codex_decide as the live DecideFn into the pure adapter → the chosen poke-env Move
    moves = [_Move("thunderbolt", 90), _Move("tackle", 40)]
    chosen = select_codex_move(
        _Harness(),
        _Battle(moves),
        decide=lambda h, c: codex_decide(h, c, run=lambda p, s, t: {"move_id": "thunderbolt"}),
    )
    assert chosen is moves[0]
