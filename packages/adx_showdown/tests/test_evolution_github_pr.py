"""Closed-loop GitHub publisher (ADX evolution → PR) — sidecar-free.

Covers (1) the gh_pr_publisher end-to-end offline: a real local git push to a
bare repo + an injected fake `gh` runner, and (2) the run_generation cadence
gate: publish on a MEASURED verdict / rollback, skip NEUTRAL.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from adx_showdown import evolution as evo
from adx_showdown.evolution import (
    EvolutionLoop,
    GenerationReport,
    HarnessWorkspace,
    _pr_body,
    gh_pr_publisher,
)
from adx_showdown.sim import BattleResult
from agentdex_engine.cards import EvolutionCard, Seed


def _card(gen: int = 1) -> EvolutionCard:
    return EvolutionCard(
        expedition_id=f"arena-gen-{gen}",
        parent_lineage_root=None,
        winning_pattern="rating 1520±90",
        losing_pattern="",
        mutation_seeds={
            "harness": [
                Seed(
                    kind="team_mutation",
                    description="swap lead",
                    evidence_jsonl_excerpt="{}",
                    confidence="high",
                    seed_provenance="learned",
                )
            ]
        },
        boundary_annotations=["verdict=EFFECTIVE"],
    )


def _report(gen: int = 1, verdict: str = "EFFECTIVE") -> GenerationReport:
    return GenerationReport(
        generation=gen,
        commit="abc123",
        verdict=verdict,  # type: ignore[arg-type]
        paired_pairs=5,
        p_value=0.02,
        glicko_delta=12.0,
        rating=1520.0,
        rd=90.0,
        power_verdict="POWERED",
        manifest_summary="swap lead",
    )


def test_pr_body_carries_verdict_and_metrics() -> None:
    body = _pr_body(_report(), _card())
    assert "generation 1" in body
    assert "EFFECTIVE" in body
    assert "glicko_delta: 12.0" in body
    assert "evolution_card.json" in body


def test_gh_pr_publisher_pushes_branch_and_opens_pr(tmp_path: Path) -> None:
    # A real local bare repo stands in for GitHub — the push is genuine (offline);
    # only `gh pr create` is faked via an injected runner.
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    ws = HarnessWorkspace.init(tmp_path / "ws", team_packed="packed-team-v0")

    calls: list[list[str]] = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="https://github.com/o/r/pull/7\n", returncode=0)

    publish = gh_pr_publisher("o/r", remote_url=str(bare), runner=fake_runner)
    url = publish(ws, _report(gen=1, verdict="EFFECTIVE"), _card(1))

    # the publisher returned the PR url from `gh`
    assert url == "https://github.com/o/r/pull/7"
    # the card artifact landed in the workspace
    assert (ws.root / "evolution_card.json").is_file()
    # the generation branch was really pushed to the (bare) remote
    refs = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare)], capture_output=True, text=True, check=True
    ).stdout
    assert "evolution/gen-1-effective" in refs
    # `gh pr create` was invoked with the right repo/head/base
    gh_call = next(c for c in calls if c[:3] == ["gh", "pr", "create"])
    assert "--repo" in gh_call and "o/r" in gh_call
    assert "evolution/gen-1-effective" in gh_call
    assert "--base" in gh_call and "main" in gh_call


# ---- cadence gate (sidecar-free run_generation with faked windows) ----


def _loop_with_fake_windows(tmp_path: Path, pr_publisher) -> EvolutionLoop:
    ws = HarnessWorkspace.init(tmp_path / "ws", team_packed="packed-team-v0")
    loop = EvolutionLoop(
        workspace=ws,
        opponent_factory=lambda *_a: None,
        events_path=tmp_path / "events.jsonl",
        pr_publisher=pr_publisher,
        k_battles=2,
    )

    async def fake_window(sidecar, *, team, gen, label):
        # live always wins; the verdict is forced via mcnemar_verdict below.
        return [
            BattleResult(battle_id=f"{label}-g{gen}-b{i}", winner="house-evolver", turns=4)
            for i in range(loop.k_battles)
        ]

    loop._window = fake_window  # type: ignore[method-assign]
    loop._rate = lambda results, gen: (1500.0, 100.0, 5.0)  # type: ignore[method-assign]
    return loop


def test_cadence_skips_neutral_generation(tmp_path: Path) -> None:
    seen: list[str] = []
    loop = _loop_with_fake_windows(tmp_path, lambda ws, rep, card: seen.append(rep.verdict))
    # gen 0 has no pending manifest -> verdict stays NEUTRAL -> NO publish.
    import asyncio

    rep = asyncio.run(loop.run_generation(None, 0))
    assert rep.verdict == "NEUTRAL"
    assert seen == []  # NEUTRAL is PR noise — skipped
    assert rep.pr_url is None


def test_cadence_publishes_effective_generation(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    seen: list[tuple[str, int]] = []

    def fake_pub(ws, rep, card):
        seen.append((rep.verdict, rep.generation))
        return "https://github.com/o/r/pull/9"

    loop = _loop_with_fake_windows(tmp_path, fake_pub)
    # Force an EFFECTIVE verdict from the paired window.
    monkeypatch.setattr(
        evo,
        "mcnemar_verdict",
        lambda paired, **k: SimpleNamespace(verdict="EFFECTIVE", p_value=0.01),
    )
    # A pending manifest targeting gen 1 makes gen 1 a measured (falsifiable) edit.
    loop.workspace.write_manifest(
        evo.ChangeManifest(generation=1, summary="swap lead", edited_stores=["teams.json"])
    )
    rep = asyncio.run(loop.run_generation(None, 1))

    assert rep.verdict == "EFFECTIVE"
    assert seen == [("EFFECTIVE", 1)]  # measured move -> published
    assert rep.pr_url == "https://github.com/o/r/pull/9"
