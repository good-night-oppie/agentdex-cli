"""Phase-A7 — house-lane evolution loop (A4/A5 gate anchors).

Criteria:
- ≥3 generations × k≥5 battles, verdicts computed only at the NEXT window
- injected one-Pokémon-class team nerf detected HARMFUL in ≤50 CRN pairs
- HARMFUL auto-rolls back to best_ever (chaos drill, transcript printed)
- evolving-vs-frozen delta reported with RD; underpowered → INCONCLUSIVE
- one EvolutionCard per generation, chained via parent_lineage_root
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from adx_showdown.bots import max_damage_bot, random_bot
from adx_showdown.evolution import (
    ChangeManifest,
    EvolutionLoop,
    HarnessWorkspace,
)
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.teams import pack_team, starter_pack, validate_team

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


def _nerf_team_export() -> str:
    """Five weak early-route mons + one survivor — a brutal, VALID gen9ou nerf."""
    blocks = [
        "Magikarp @ Focus Sash\nAbility: Swift Swim\nEVs: 252 HP / 252 Spe\nJolly Nature\n- Tackle\n- Splash\n- Flail",
        "Lechonk @ Leftovers\nAbility: Thick Fat\nEVs: 252 HP / 252 Def\nImpish Nature\n- Tackle\n- Covet",
        "Tarountula @ Leftovers\nAbility: Insomnia\nEVs: 252 HP / 252 Def\nImpish Nature\n- Bug Bite\n- String Shot",
        "Fletchling @ Leftovers\nAbility: Big Pecks\nEVs: 252 HP / 252 Spe\nJolly Nature\n- Peck\n- Quick Attack",
        "Pawmi @ Leftovers\nAbility: Static\nEVs: 252 HP / 252 Spe\nJolly Nature\n- Thunder Shock\n- Quick Attack",
        "Wattrel @ Leftovers\nAbility: Wind Power\nEVs: 252 HP / 252 Spe\nJolly Nature\n- Peck\n- Thunder Shock",
    ]
    return "\n\n".join(blocks)


@pytest.fixture(scope="module")
def packed_teams() -> dict[str, str]:
    async def _pack() -> dict[str, str]:
        async with Sidecar() as sc:
            base = await pack_team(sc, starter_pack()["01-balance-tusk-gambit"])
            nerf = await pack_team(sc, _nerf_team_export())
            ok, errors = await validate_team(sc, nerf)
            assert ok, f"nerf team must be VALID gen9ou (only weak): {errors}"
            return {"base": base, "nerf": nerf}

    return asyncio.run(_pack())


def test_workspace_lifecycle_and_rollback_bytes(tmp_path: Path, packed_teams):
    ws = HarnessWorkspace.init(tmp_path / "ws", team_packed=packed_teams["base"])
    shas0 = ws.store_shas()
    # mutate two stores, commit, then roll back
    (ws.root / "teams.json").write_text(json.dumps({"active": packed_teams["nerf"]}) + "\n")
    (ws.root / "memory.json").write_text('["bad idea"]\n')
    ws.commit_edits("nerf applied")
    assert ws.store_shas() != shas0
    ws.rollback_to_best_ever()
    assert ws.store_shas() == shas0, "rollback must restore stores byte-identically"


@pytest.mark.timeout(900)
def test_three_generations_next_window_verdicts(tmp_path: Path, packed_teams):
    """Criteria 1+3: ≥3 generations, k≥5; verdicts only at the NEXT window;
    deltas carry RD; underpowered windows marked INCONCLUSIVE."""
    edits_seen: list[int] = []

    def benign_refiner(ws: HarnessWorkspace, distilled: str, gen: int) -> ChangeManifest:
        # memory-store note: a real edit, intentionally team-neutral, so the
        # CRN verdict on the TEAM is INCONCLUSIVE (honest: no measurable claim)
        (ws.root / "memory.json").write_text(json.dumps([f"note for gen {gen}"]) + "\n")
        edits_seen.append(gen)
        return ChangeManifest(
            generation=gen,
            summary=f"memory note gen {gen}",
            edited_stores=["memory.json"],
            predicted_fixes=["none (team unchanged)"],
        )

    async def _run():
        ws = HarnessWorkspace.init(tmp_path / "ws", team_packed=packed_teams["base"])
        loop = EvolutionLoop(
            workspace=ws,
            opponent_factory=lambda sc, seed: max_damage_bot(sc, fallback_seed=seed),
            events_path=tmp_path / "events.jsonl",
            refiner=benign_refiner,
            k_battles=5,
            opponent_team=packed_teams["base"],
        )
        async with Sidecar() as sc:
            for gen in (1, 2, 3):
                await loop.run_generation(sc, gen)
        return loop

    loop = asyncio.run(_run())
    assert len(loop.reports) == 3
    print("\nGENERATIONS:")
    for r in loop.reports:
        delta = (
            f"{r.glicko_delta:+.1f}"
            if r.glicko_delta is not None
            else f"INCONCLUSIVE(<2RD={2 * r.rd:.0f})"
        )
        print(
            f"  gen {r.generation}: verdict={r.verdict} pairs={r.paired_pairs} "
            f"p={r.p_value} rating={r.rating:.0f}±{r.rd:.0f} delta={delta} power={r.power_verdict}"
        )
    # gen 1 had NO prior manifest -> no falsification window (NEUTRAL, 0 pairs)
    assert loop.reports[0].verdict == "NEUTRAL" and loop.reports[0].paired_pairs == 0
    # gens 2+3 falsify the PREVIOUS cycle's edit: k pairs each
    for r in loop.reports[1:]:
        assert r.paired_pairs == 5, "next-window falsification must run k pairs"
        assert r.verdict in ("INCONCLUSIVE", "EFFECTIVE", "HARMFUL")
    assert edits_seen == [2, 3, 4], "refiner runs at END of each cycle for the next gen"
    # A4: every report carries rating ± RD; small windows are honestly underpowered
    assert all(r.rd > 0 for r in loop.reports)


@pytest.mark.timeout(900)
def test_injected_nerf_detected_harmful_and_rolled_back(tmp_path: Path, packed_teams):
    """Criteria 2+4: one-Pokémon-class nerf -> HARMFUL in ≤50 CRN pairs ->
    automatic rollback to best_ever (chaos drill transcript below)."""

    def nerf_refiner(ws: HarnessWorkspace, distilled: str, gen: int) -> ChangeManifest | None:
        if gen != 2:
            return None
        (ws.root / "teams.json").write_text(
            json.dumps({"active": packed_teams["nerf"]}, indent=1) + "\n"
        )
        return ChangeManifest(
            generation=2,
            summary="INJECTED NERF: team swapped to early-route mons",
            edited_stores=["teams.json"],
            predicted_fixes=["(deliberately harmful — regression probe)"],
            risk_matchups=["everything"],
        )

    async def _run():
        ws = HarnessWorkspace.init(tmp_path / "ws", team_packed=packed_teams["base"])
        loop = EvolutionLoop(
            workspace=ws,
            # falsification needs an opponent the BASE team reliably beats —
            # in a max-damage MIRROR the entrant loses most seeds (measured:
            # control loses too, pairs go concordant, p=0.5). Random anchor:
            # base wins big, nerf loses big -> discordant pairs -> HARMFUL.
            opponent_factory=lambda sc, seed: random_bot(seed),
            events_path=tmp_path / "events.jsonl",
            refiner=nerf_refiner,
            k_battles=20,  # ≤50 criterion
            opponent_team=packed_teams["base"],
        )
        async with Sidecar() as sc:
            healthy_shas = ws.store_shas()
            r1 = await loop.run_generation(sc, 1)  # applies nerf at cycle end
            nerfed_shas = ws.store_shas()
            r2 = await loop.run_generation(sc, 2)  # falsifies -> HARMFUL -> rollback
            return loop, r1, r2, healthy_shas, nerfed_shas, ws

    loop, r1, r2, healthy_shas, nerfed_shas, ws = asyncio.run(_run())
    print("\nROLLBACK_DRILL transcript:")
    print(f"  1. healthy gen-1 window: rating={r1.rating:.0f}±{r1.rd:.0f}")
    print(f"  2. nerf committed for gen 2 (teams.json sha {nerfed_shas['teams.json'][:8]})")
    print(
        f"  3. gen-2 CRN falsification: {r2.paired_pairs} pairs, p={r2.p_value:.5f} "
        f"-> verdict={r2.verdict}"
    )
    print(
        f"  4. rolled_back={r2.rolled_back}; teams.json sha now {ws.store_shas()['teams.json'][:8]}"
    )
    assert r2.paired_pairs <= 50
    assert r2.verdict == "HARMFUL", f"nerf not detected: p={r2.p_value}"
    assert r2.rolled_back
    assert ws.store_shas()["teams.json"] == healthy_shas["teams.json"], (
        "rollback must restore the healthy team byte-identically"
    )


def test_evolution_card_chain_via_kaos(tmp_path: Path):
    """Criterion 5: one EvolutionCard per generation, chained via
    parent_lineage_root in KAOS lineage."""
    import sqlite3

    from adx_showdown.evolution import GenerationReport
    from agentdex_engine.shared.kaos_adapter import log_expedition_lineage

    reports = [
        GenerationReport(
            generation=g,
            commit="c" * 8,
            verdict="INCONCLUSIVE",
            paired_pairs=5,
            rating=1500 + g,
            rd=120.0,
            power_verdict="INCONCLUSIVE",
        )
        for g in (1, 2)
    ]
    ws_loop = EvolutionLoop.__new__(EvolutionLoop)  # only evolution_card needed
    card1 = ws_loop.evolution_card(reports[0], parent_lineage_root=None)
    db = tmp_path / "kaos.db"
    id1 = log_expedition_lineage(db, card1.expedition_id, card1.model_dump(mode="json"))
    card2 = ws_loop.evolution_card(reports[1], parent_lineage_root=id1)
    id2 = log_expedition_lineage(
        db, card2.expedition_id, card2.model_dump(mode="json"), parent_lineage_root=id1
    )
    rows = dict(sqlite3.connect(db).execute("SELECT agent_id, parent_id FROM agents").fetchall())
    assert rows[id2] == id1, "generation 2 must chain to generation 1's lineage root"
    assert card2.parent_lineage_root == id1
    print(f"\nEVOLUTION_CHAIN: gen1={id1} <- gen2={id2}")
