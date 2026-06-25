"""skills.json is now LOAD-BEARING (the 2nd of the 4 inert Refiner stores).

#600 wired prompt.md onto the behavioral path; subagents.json/skills.json/
memory.json stayed inert — written + committed but never read, so the Refiner
could edit them forever and the falsification rail could not measure any of it
(the ADR-0014 load-bearing-stores note; locked by test_store_read_tracing).

This wires skills.json: its raw text joins the entrant's steering directive
(``EvolutionLoop._live_directive``), so a Refiner edit that writes a strategy
keyword into skills.json now MOVES play — and the control window freezes it
(``_skills_at_tag`` / ``_frozen_directive``) so the CRN McNemar comparison can
measure the edit. The empty default ``"[]"`` carries no keyword, so prompt.md's
surface and house behavior are unchanged (no regression to #600).
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


def test_default_skills_does_not_change_house_behavior(tmp_path: Path):
    """Default skills.json ("[]") adds no keyword, so the directive == the
    prompt-only behavior: the default house prompt still maps to max_damage.
    No silent regression to the prompt.md surface (#600)."""
    loop = _loop(_ws(tmp_path), tmp_path)
    assert select_strategy(loop._live_directive()) == "max_damage"


def test_skills_keyword_steers_the_directive(tmp_path: Path):
    """A strategy keyword written into skills.json moves the selected archetype,
    even when the prompt is the neutral default — this is what makes skills.json
    load-bearing: editing it changes play."""
    ws = _ws(tmp_path)
    (ws.root / "skills.json").write_text('["prefer defensive stall and recover"]\n')
    ws.commit_edits("skills -> stall")
    assert select_strategy(_loop(ws, tmp_path)._live_directive()) == "stall"

    # skills can escalate past the prompt by strategy priority (stall > offense)
    ws2 = _ws(tmp_path / "b", prompt="aggressive sweeper")
    (ws2.root / "skills.json").write_text('["play defensive stall"]\n')
    ws2.commit_edits("skills -> stall over offense prompt")
    assert select_strategy(_loop(ws2, tmp_path / "b")._live_directive()) == "stall"


def test_control_window_freezes_skills(tmp_path: Path):
    """CRN invariant: the control directive must steer from the gen-(N-1) skills,
    not the live one — else a skills-only edit steers both windows identically and
    McNemar can never measure it (mirrors test_control_window_freezes_the_prompt)."""
    ws = _ws(tmp_path)
    (ws.root / "skills.json").write_text('["aggressive offense"]\n')
    ws.commit_edits("seed gen-0 skills")
    ws.tag_state("gen-0")  # freeze gen-0 at the aggressive skills
    # the Refiner edits skills.json for the next generation
    (ws.root / "skills.json").write_text('["defensive stall recover"]\n')
    ws.commit_edits("edit skills for gen 1")
    loop = _loop(ws, tmp_path)
    frozen = select_strategy(loop._frozen_directive("gen-0"))
    live = select_strategy(loop._live_directive())
    assert frozen == "offense"  # pre-edit skills steers the control window
    assert live == "stall"  # edited skills steers the live window
    assert frozen != live  # measurable difference


def test_skills_is_read_on_the_behavioral_path(tmp_path: Path):
    """LOAD-BEARING proof: building the live directive reads skills.json (via
    workspace.skills), so it registers in trace_store_reads — it was 0 before this
    wire. If skills.json is ever un-wired, this assertion goes RED."""
    loop = _loop(_ws(tmp_path), tmp_path)
    with trace_store_reads() as reads:
        loop._live_directive()
    assert reads["skills.json"] >= 1
    assert reads["prompt.md"] >= 1  # prompt.md stays wired too
    assert reads["teams.json"] == 0  # the directive does not touch teams.json
