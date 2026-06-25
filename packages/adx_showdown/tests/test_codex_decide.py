"""L1 — the live codex move hook. Unit-tested with an INJECTED fake codex runner so
CI never shells out; a real codex CLI is exercised only by the gated live smoke."""

from __future__ import annotations

import os
import subprocess
import sys

from adx_showdown.selfplay.codex_adapter import codex_context, select_codex_move
from adx_showdown.selfplay.codex_decide import (
    _build_prompt,
    _clean_considered,
    _codex_exec_args,
    _parse_last_json,
    _timeout_sec,
    codex_decide,
    codex_decide_explain,
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


def test_codex_decide_passes_an_illegal_pick_through_for_the_adapter_to_gate():
    """codex_decide does NOT swallow an illegal pick — it returns codex's proposed id
    so the adapter (select_codex_move) can COUNT it as illegal and substitute a legal
    order. Pre-filtering to None here would mask live illegal choices as abstentions
    (review #3440261654)."""
    ctx = _ctx([_Move("thunderbolt", 90)])
    assert (
        codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "hyperbeam"}) == "hyperbeam"
    )


def test_live_illegal_choice_is_counted_through_the_adapter():
    """End-to-end: a live codex CLI that returns an illegal id must increment the
    illegal counter (not be silently treated as an abstention)."""
    moves = [_Move("thunderbolt", 90)]
    calls = []
    chosen = select_codex_move(
        _Harness(),
        _Battle(moves),
        decide=lambda h, c: codex_decide(h, c, run=lambda p, s, t: {"move_id": "hyperbeam"}),
        on_illegal=lambda: calls.append(1),
    )
    assert calls == [1]  # the live illegal choice WAS counted
    assert chosen is moves[0]  # ...and a legal move substituted


def test_codex_decide_abstains_on_a_blank_pick():
    ctx = _ctx([_Move("thunderbolt", 90)])
    assert codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "  "}) is None


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
    # an off-roster pick is passed through for the adapter to gate + count (not masked)
    assert codex_decide(_Harness(), ctx, run=lambda p, s, t: {"move_id": "mewtwo"}) == "mewtwo"


def test_prompt_offers_legal_switches():
    ctx = _ctx([_Move("ember", 40)], switches=[_Switch("blastoise")])
    prompt = _build_prompt(_Harness(), ctx, ["ember", "blastoise"])
    assert "Legal switches" in prompt and "blastoise" in prompt


def test_parse_last_json_takes_the_last_block():
    assert _parse_last_json('noise {"a": 1} more {"move_id": "surf"}') == {"move_id": "surf"}


def test_live_codex_invocation_is_readonly_and_ephemeral():
    """The per-turn move hook must not give an evolved prompt a write-capable Codex
    session. It should use Codex's read-only sandbox rather than the dangerous
    bypass flag (review #3440165074)."""
    args = _codex_exec_args("codex", "schema.json", "last.txt", "pick thunderbolt")
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args


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


# ---- explain-capture (attested candidate fan; arena2d mind-readout) ----


def test_explain_default_prompt_is_byte_identical_to_the_live_prompt():
    """The live decision path must be UNCHANGED: _build_prompt(explain=False) is exactly
    the prompt codex_decide sends, so evolution / battle calls pay no extra tokens and
    carry no perturbation risk from the capture feature."""
    ctx = _ctx([_Move("surf", 90), _Move("tackle", 40)])
    assert _build_prompt(_Harness(), ctx, ["surf", "tackle"]) == _build_prompt(
        _Harness(), ctx, ["surf", "tackle"], explain=False
    )


def test_explain_prompt_asks_for_the_considered_set():
    ctx = _ctx([_Move("surf", 90), _Move("tackle", 40)])
    prompt = _build_prompt(_Harness(), ctx, ["surf", "tackle"], explain=True)
    assert "considered" in prompt and "why_not" in prompt
    # still carries the live essentials (policy + legal ids)
    assert "Prefer super-effective coverage" in prompt
    assert "surf" in prompt and "tackle" in prompt


def test_codex_decide_explain_returns_chosen_plus_considered():
    ctx = _ctx([_Move("stoneedge", 100), _Move("crunch", 80), _Move("icepunch", 75)])
    out = codex_decide_explain(
        _Harness(),
        ctx,
        run=lambda p, s, t: {
            "move_id": "stoneedge",
            "rationale": "4x weak to Rock",
            "considered": [
                {"move_id": "crunch", "why_not": "only neutral"},
                {"move_id": "icepunch", "why_not": "resisted"},
            ],
        },
    )
    assert out is not None
    assert out["move_id"] == "stoneedge"
    assert out["rationale"] == "4x weak to Rock"
    assert [c["move_id"] for c in out["considered"]] == ["crunch", "icepunch"]


def test_codex_decide_explain_defaults_considered_to_empty():
    ctx = _ctx([_Move("thunderbolt", 90)])
    out = codex_decide_explain(
        _Harness(), ctx, run=lambda p, s, t: {"move_id": "thunderbolt", "rationale": "ok"}
    )
    assert out == {"move_id": "thunderbolt", "rationale": "ok", "considered": []}


def test_codex_decide_explain_is_failsafe_on_error():
    def boom(p, s, t):
        raise RuntimeError("codex down")

    out = codex_decide_explain(_Harness(), _ctx([_Move("thunderbolt", 90)]), run=boom)
    assert out is None


def test_codex_decide_explain_abstains_on_blank_pick():
    out = codex_decide_explain(
        _Harness(), _ctx([_Move("thunderbolt", 90)]), run=lambda p, s, t: {"move_id": "  "}
    )
    assert out is None


def test_codex_decide_explain_no_legal_moves_returns_none():
    assert codex_decide_explain(_Harness(), _ctx([]), run=lambda p, s, t: {"move_id": "x"}) is None


def test_explain_uses_the_explain_schema_not_the_live_schema():
    """The capture call must request the considered field via the schema, else strict
    output would never emit it."""
    seen: dict = {}

    def fake_run(prompt, schema, timeout):
        seen["schema"] = schema
        return {"move_id": "thunderbolt", "rationale": "x", "considered": []}

    codex_decide_explain(_Harness(), _ctx([_Move("thunderbolt", 90)]), run=fake_run)
    props = seen["schema"]["properties"]
    assert "considered" in props
    assert props["considered"]["items"]["required"] == ["move_id", "why_not"]


def test_clean_considered_drops_chosen_hallucinated_and_dupes():
    legal = {"stoneedge", "crunch", "icepunch", "firepunch"}
    raw = [
        {"move_id": "stoneedge", "why_not": "but this IS the pick"},  # self-reference → drop
        {"move_id": "earthquake", "why_not": "not legal"},  # hallucinated → drop
        {"move_id": "crunch", "why_not": "neutral"},  # keep
        {"move_id": "crunch", "why_not": "dup"},  # duplicate → drop
        {"move_id": "icepunch", "why_not": "resisted"},  # keep
        "not-a-dict",  # malformed → drop
    ]
    out = _clean_considered(raw, chosen="stoneedge", legal=legal)
    assert [c["move_id"] for c in out] == ["crunch", "icepunch"]


def test_clean_considered_caps_at_four():
    legal = {f"m{i}" for i in range(10)}
    raw = [{"move_id": f"m{i}", "why_not": "n"} for i in range(10)]
    assert len(_clean_considered(raw, chosen="x", legal=legal)) == 4
