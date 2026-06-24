"""Observability lock for the 'load-bearing surface' of the 5-store workspace.

Consensus 2026-06-16 (adx-cli-9): originally only `teams.json` was behaviorally
read. As of A2A #1271, `prompt.md` is ALSO load-bearing — the entrant policy is
steered by `workspace.system_prompt` (see `prompt_steered_policy_factory` and
test_prompt_load_bearing, which pins prompt.md's read + battle-divergence). The
remaining three (subagents.json, skills.json, memory.json) are still written +
committed but never read, so an LLM Refiner editing them produces unmeasurable
no-ops (the 'measurement illusion' the falsification rail cannot catch).

`trace_store_reads` makes that surface observable; these tests pin it as a
RED-on-regression invariant. When a follow-up PR wires a store into the policy
(making it load-bearing), its read WILL show up here and the relevant assertion
MUST be updated in the SAME PR — that is the point (as prompt.md just was).

Sidecar-free: only HarnessWorkspace (git) is exercised; no Node battle stream.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.evolution import STORE_FILES, HarnessWorkspace, trace_store_reads

_TEAM = "Pikachu||Light Ball|Static|Thunderbolt||||||"


def _ws(tmp_path: Path) -> HarnessWorkspace:
    return HarnessWorkspace.init(tmp_path / "ws", team_packed=_TEAM)


def test_team_read_traces_only_teams_store(tmp_path: Path):
    """The loop's ONLY behavioral store read (`workspace.team`) touches teams.json
    and nothing else — the dark-store invariant."""
    ws = _ws(tmp_path)
    with trace_store_reads() as reads:
        assert ws.team == _TEAM
    assert dict(reads) == {"teams.json": 1}
    # `workspace.team` itself touches ONLY teams.json. prompt.md is now read on a
    # DIFFERENT behavioral path (the entrant policy — see test_prompt_load_bearing);
    # the remaining three stores are still never read on any behavioral path.
    for dark in ("prompt.md", "subagents.json", "skills.json", "memory.json"):
        assert reads[dark] == 0


def test_trace_records_every_store_it_is_asked_to_read(tmp_path: Path):
    """Tracer correctness: read_store records EVERY store read, so when one of the
    inert stores is wired into the policy its reads will become visible here."""
    ws = _ws(tmp_path)
    with trace_store_reads() as reads:
        for store in STORE_FILES:
            ws.read_store(store)
    assert dict(reads) == {store: 1 for store in STORE_FILES}


def test_store_shas_is_not_traced_as_a_behavioral_read(tmp_path: Path):
    """Integrity hashing (store_shas) reads all five files but is NOT a behavioral
    read — it must stay out of the trace so the load-bearing signal is honest."""
    ws = _ws(tmp_path)
    with trace_store_reads() as reads:
        ws.store_shas()
    assert dict(reads) == {}


def test_trace_resets_after_block(tmp_path: Path):
    """Reads outside any trace block are not recorded (ContextVar reset)."""
    ws = _ws(tmp_path)
    with trace_store_reads() as first:
        _ = ws.team
    assert dict(first) == {"teams.json": 1}
    # second independent block sees only its own reads
    with trace_store_reads() as second:
        ws.read_store("memory.json")
    assert dict(second) == {"memory.json": 1}
