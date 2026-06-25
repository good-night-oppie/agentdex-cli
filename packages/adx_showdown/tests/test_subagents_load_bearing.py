"""subagents.json is now LOAD-BEARING (the 3rd of the 4 inert Refiner stores).

#600 wired prompt.md, #607 wired skills.json; subagents.json + memory.json were
the remaining inert stores — written + committed but never read, so the Refiner
could edit them forever and the falsification rail could not measure any of it
(ADR-0014 load-bearing-stores note; locked by test_store_read_tracing).

This wires subagents.json: its raw text joins the entrant's steering directive
(``EvolutionLoop._live_directive``), so a Refiner edit that writes a strategy
keyword into subagents.json now MOVES play — and the control window freezes it
(``_subagents_at_tag`` / ``_frozen_directive``) so the CRN McNemar comparison can
measure the edit. The empty default ``"[]"`` carries no keyword, so the prompt.md
+ skills.json surface and house behavior are unchanged (no regression).
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.evolution import (
    EvolutionLoop,
    HarnessWorkspace,
    select_strategy,
    trace_store_reads,
)

_TEAM = "Pikachu||LightBall|Static|Thunderbolt,VoltSwitch||||||"


def _loop(ws: HarnessWorkspace, tmp: Path) -> EvolutionLoop:
    return EvolutionLoop(
        workspace=ws, opponent_factory=lambda sc, s: None, events_path=tmp / "ev.jsonl"
    )


def _ws(tmp: Path, *, prompt: str = "house battler v0") -> HarnessWorkspace:
    return HarnessWorkspace.init(tmp / "ws", team_packed=_TEAM, prompt=prompt)


def test_default_subagents_does_not_change_house_behavior(tmp_path: Path):
    """Default subagents.json ("[]") adds no keyword, so the directive == the
    prompt+skills behavior: the default house prompt still maps to max_damage.
    No silent regression to the prompt.md / skills.json surface."""
    loop = _loop(_ws(tmp_path), tmp_path)
    assert select_strategy(loop._live_directive()) == "max_damage"


def test_subagents_keyword_steers_the_directive(tmp_path: Path):
    """A strategy keyword written into subagents.json moves the selected archetype,
    even when prompt + skills are the neutral default — this is what makes
    subagents.json load-bearing: editing it changes play."""
    ws = _ws(tmp_path)
    (ws.root / "subagents.json").write_text('["lead with trick room"]\n')
    ws.commit_edits("subagents -> trickroom")
    assert select_strategy(_loop(ws, tmp_path)._live_directive()) == "trickroom"


def test_control_window_freezes_subagents(tmp_path: Path):
    """CRN invariant: the control directive must steer from the gen-(N-1)
    subagents, not the live one — else a subagents-only edit steers both windows
    identically and McNemar can never measure it."""
    ws = _ws(tmp_path)
    (ws.root / "subagents.json").write_text('["aggressive offense"]\n')
    ws.commit_edits("seed gen-0 subagents")
    ws.tag_state("gen-0")  # freeze gen-0 at the aggressive subagents
    # the Refiner edits subagents.json for the next generation
    (ws.root / "subagents.json").write_text('["defensive stall recover"]\n')
    ws.commit_edits("edit subagents for gen 1")
    loop = _loop(ws, tmp_path)
    frozen = select_strategy(loop._frozen_directive("gen-0"))
    live = select_strategy(loop._live_directive())
    assert frozen == "offense"  # pre-edit subagents steers the control window
    assert live == "stall"  # edited subagents steers the live window
    assert frozen != live  # measurable difference


def test_subagents_is_read_on_the_behavioral_path(tmp_path: Path):
    """LOAD-BEARING proof: building the live directive reads subagents.json (via
    workspace.subagents), so it registers in trace_store_reads — it was 0 before
    this wire. If subagents.json is ever un-wired, this assertion goes RED."""
    loop = _loop(_ws(tmp_path), tmp_path)
    with trace_store_reads() as reads:
        loop._live_directive()
    assert reads["subagents.json"] >= 1
    assert reads["prompt.md"] >= 1  # prompt.md stays wired
    assert reads["skills.json"] >= 1  # skills.json stays wired
    assert reads["teams.json"] == 0  # the directive does not touch teams.json
