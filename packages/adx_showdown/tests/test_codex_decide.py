"""L1 — the live codex move hook. Unit-tested with an INJECTED fake codex runner so
CI never shells out; a real codex CLI is exercised only by the gated live smoke."""

from __future__ import annotations

import os
import subprocess
import sys

from adx_showdown.selfplay.codex_adapter import codex_context, select_codex_move
from adx_showdown.selfplay.codex_decide import (
    _build_prompt,
    _parse_last_json,
    _timeout_sec,
    codex_decide,
)


class _Move:
    def __init__(self, mid: str, base_power: int) -> None:
        self.id = mid
        self.base_power = base_power


class _Switch:
    def __init__(self, species: str) -> None:
        self.species = species


class _Battle:
    def __init__(self, moves: list[_Move], switches: list[_Switch] | None = None) -> None:
        self.available_moves = moves
        self.available_switches = switches or []
        self.active_pokemon = None
        self.force_switch = False


class _Harness:
    system_prompt = "Prefer super-effective coverage; never stall."
    params: dict = {}


def _ctx(moves: list[_Move], switches: list[_Switch] | None = None) -> dict:
    return codex_context(_Battle(moves, switches))


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


def test_codex_decide_can_return_a_switch_species():
    """A live policy can pick a switch — the species is in the legal-id set, so
    codex_decide accepts it (and the adapter turns it into a switch order)."""
    ctx = _ctx([_Move("ember", 40)], switches=[_Switch("blastoise")])
    out = codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "blastoise"})
    assert out == "blastoise"


def test_codex_decide_on_forced_switch_offers_only_switches():
    """KO → no moves, only switches: the switch species are the legal ids."""
    ctx = _ctx([], switches=[_Switch("venusaur"), _Switch("snorlax")])
    out = codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "snorlax"})
    assert out == "snorlax"
    # an off-roster pick is still rejected (fail-safe → None → random legal order)
    assert codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "mewtwo"}) is None


def test_prompt_offers_legal_switches():
    ctx = _ctx([_Move("ember", 40)], switches=[_Switch("blastoise")])
    prompt = _build_prompt(_Harness(), ctx, ["ember", "blastoise"])
    assert "Legal switches" in prompt and "blastoise" in prompt


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


# ---- crash-safe timeout override (PR #344 review #3440165077) ----


def test_timeout_sec_honors_a_valid_override(monkeypatch):
    monkeypatch.setenv("ADX_CODEX_TIMEOUT_SEC", "12.5")
    assert _timeout_sec() == 12.5


def test_timeout_sec_falls_back_on_a_malformed_override(monkeypatch):
    monkeypatch.setenv("ADX_CODEX_TIMEOUT_SEC", "not-a-number")
    assert _timeout_sec() == 60.0  # never raises — the live hook must not crash a battle


def test_codex_decide_uses_the_default_timeout_on_a_malformed_env(monkeypatch):
    """A mistyped override must not abort the battle: codex_decide still resolves a
    move and the run hook receives the default (60s), not a ValueError."""
    monkeypatch.setenv("ADX_CODEX_TIMEOUT_SEC", "garbage")
    seen: dict[str, float] = {}

    def fake_run(prompt, schema, timeout):
        seen["timeout"] = timeout
        return {"move_id": "thunderbolt"}

    out = codex_decide(_Harness(), _ctx([_Move("thunderbolt", 90)]), run=fake_run)
    assert out == "thunderbolt"
    assert seen["timeout"] == 60.0


def test_importing_module_survives_a_malformed_timeout_env():
    """Regression: parsing ADX_CODEX_TIMEOUT_SEC at MODULE scope raised ValueError on
    a mistyped value BEFORE codex_decide's fail-safe try/except — crashing the runner's
    lazy ``import codex_decide`` (→ aborting the battle). Import must now be crash-safe."""
    env = {**os.environ, "ADX_CODEX_TIMEOUT_SEC": "not-a-number"}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import adx_showdown.selfplay.codex_decide as cd; print(cd._timeout_sec())",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr  # pre-fix: ValueError at import time
    assert proc.stdout.strip() == "60.0"
