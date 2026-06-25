"""memory.json is now LOAD-BEARING — the LAST of the 4 inert Refiner stores.

#600 wired prompt.md, #607 wired skills.json, #608 wired subagents.json. memory.json
was the final inert store — written + committed but never read, so the Refiner
could edit it forever and the falsification rail could not measure it (ADR-0014
load-bearing-stores note; locked by test_store_read_tracing).

With this wire the FULL Refiner surface (all four text stores) is read on the
behavioral path and frozen in the CRN control window, so an edit to ANY of them is
measurable. memory.json's raw text joins the entrant's steering directive
(``EvolutionLoop._live_directive``) and is frozen via ``_memory_at_tag`` /
``_frozen_directive``. The empty default ``"[]"`` carries no keyword, so the
prompt/skills/subagents surface and house behavior are unchanged (no regression).
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.evolution import (
    STORE_FILES,
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


def test_default_memory_does_not_change_house_behavior(tmp_path: Path):
    """Default memory.json ("[]") adds no keyword, so the directive == the
    prompt+skills+subagents behavior: the default house prompt still maps to
    max_damage. No silent regression to the already-wired stores."""
    loop = _loop(_ws(tmp_path), tmp_path)
    assert select_strategy(loop._live_directive()) == "max_damage"


def test_memory_keyword_steers_the_directive(tmp_path: Path):
    """A strategy keyword written into memory.json moves the selected archetype,
    even when prompt + skills + subagents are the neutral default — this is what
    makes memory.json load-bearing: editing it changes play."""
    ws = _ws(tmp_path)
    (ws.root / "memory.json").write_text('["recall: opponent folds to aggressive offense"]\n')
    ws.commit_edits("memory -> offense")
    assert select_strategy(_loop(ws, tmp_path)._live_directive()) == "offense"


def test_control_window_freezes_memory(tmp_path: Path):
    """CRN invariant: the control directive must steer from the gen-(N-1) memory,
    not the live one — else a memory-only edit steers both windows identically and
    McNemar can never measure it."""
    ws = _ws(tmp_path)
    (ws.root / "memory.json").write_text('["aggressive offense"]\n')
    ws.commit_edits("seed gen-0 memory")
    ws.tag_state("gen-0")  # freeze gen-0 at the aggressive memory
    # the Refiner edits memory.json for the next generation
    (ws.root / "memory.json").write_text('["defensive stall recover"]\n')
    ws.commit_edits("edit memory for gen 1")
    loop = _loop(ws, tmp_path)
    frozen = select_strategy(loop._frozen_directive("gen-0"))
    live = select_strategy(loop._live_directive())
    assert frozen == "offense"  # pre-edit memory steers the control window
    assert live == "stall"  # edited memory steers the live window
    assert frozen != live  # measurable difference


def test_memory_is_read_on_the_behavioral_path(tmp_path: Path):
    """LOAD-BEARING proof: building the live directive reads memory.json (via
    workspace.memory), so it registers in trace_store_reads — it was 0 before this
    wire. If memory.json is ever un-wired, this assertion goes RED."""
    loop = _loop(_ws(tmp_path), tmp_path)
    with trace_store_reads() as reads:
        loop._live_directive()
    assert reads["memory.json"] >= 1
    assert reads["prompt.md"] >= 1  # prompt.md stays wired
    assert reads["skills.json"] >= 1  # skills.json stays wired
    assert reads["subagents.json"] >= 1  # subagents.json stays wired
    assert reads["teams.json"] == 0  # the directive does not touch teams.json


def test_all_four_refiner_text_stores_are_now_load_bearing(tmp_path: Path):
    """The whole point of #600/#607/#608/this PR: every Refiner text store is read
    on the behavioral path. teams.json is read separately (via .team); only it +
    the four text stores exist, and all five are now behaviorally consumed — the
    measurement-illusion gap (ADR-0014) is fully closed."""
    loop = _loop(_ws(tmp_path), tmp_path)
    with trace_store_reads() as reads:
        loop._live_directive()
        _ = loop.workspace.team  # teams.json read on the loop's behavioral path
    text_stores = [s for s in STORE_FILES if s != "teams.json"]
    assert all(reads[s] >= 1 for s in text_stores), {s: reads[s] for s in text_stores}
    assert reads["teams.json"] >= 1
