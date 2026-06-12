"""House-lane evolution loop — Continual-Harness × AHE merge (phase 7).

IDEAL §Arena A5 (evolution honesty), A4 (receipt):
- Five stores in a GIT workspace (prompt.md, subagents.json, skills.json,
  memory.json, teams.json — teams are the 5th store, ADR-0010); one commit +
  tag per generation; `best_ever` tag is the rollback target.
- Roles are ISOLATED: Distiller consumes ONLY structured signature bullets
  (never raw battle text — A6); Refiner CRUDs stores and MUST write
  change_manifest.json (predictions) BEFORE the next window; Verdict is pure
  Python over the NEXT window's CRN paired outcomes — no self-certification.
- HARMFUL ⇒ automatic rollback to best_ever. One generation = one
  EvolutionCard carrying the measured Glicko delta (±2·RD or INCONCLUSIVE),
  chained via parent_lineage_root.

Refiner/Distiller are injected callables: production uses LLM roles through
the platform proxy; CI uses deterministic fakes. The Verdict role is always
pure Python (the falsification rail must not be a model).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from agentdex_engine.cards import EvolutionCard, Seed
from agentdex_engine.modules.arena import (
    EventLog,
    Ladder,
    RatingEvent,
    Signature,
    extract_signatures,
    mcnemar_verdict,
    recompute_ladder,
    window_verdict,
)
from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import BattleResult, Policy, run_battle

STORE_FILES = ("prompt.md", "subagents.json", "skills.json", "memory.json", "teams.json")
GenerationVerdict = Literal["EFFECTIVE", "NEUTRAL", "HARMFUL", "INCONCLUSIVE"]


def _git(workspace: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


class HarnessWorkspace:
    """Git-init'd 5-store harness state. Refiner writes HERE only (runs/ are
    read-only to it); every generation is a commit + tag, auditable and
    revertible (AHE component observability)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @classmethod
    def init(cls, root: str | Path, *, team_packed: str, prompt: str = "") -> HarnessWorkspace:
        ws = cls(root)
        ws.root.mkdir(parents=True, exist_ok=True)
        (ws.root / "prompt.md").write_text(prompt or "house battler v0\n")
        for store in ("subagents.json", "skills.json", "memory.json"):
            (ws.root / store).write_text("[]\n")
        (ws.root / "teams.json").write_text(json.dumps({"active": team_packed}, indent=1) + "\n")
        _git(ws.root, "init", "-q")
        _git(ws.root, "config", "user.email", "arena@agentdex.local")
        _git(ws.root, "config", "user.name", "arena-evolver")
        ws.commit_edits("generation 0 (init)")
        ws.tag_state("gen-0")
        _git(ws.root, "tag", "-f", "best_ever")
        return ws

    @property
    def team(self) -> str:
        return json.loads((self.root / "teams.json").read_text())["active"]

    def store_shas(self) -> dict[str, str]:
        return {
            f: hashlib.blake2b((self.root / f).read_bytes(), digest_size=16).hexdigest()
            for f in STORE_FILES
        }

    def write_manifest(self, manifest: ChangeManifest) -> None:
        (self.root / "change_manifest.json").write_text(manifest.model_dump_json(indent=1) + "\n")

    def read_manifest(self) -> ChangeManifest | None:
        path = self.root / "change_manifest.json"
        if not path.is_file():
            return None
        return ChangeManifest.model_validate_json(path.read_text())

    def commit_edits(self, msg: str) -> str:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", msg)
        return _git(self.root, "rev-parse", "HEAD")

    def tag_state(self, tag: str) -> None:
        """Pin the CURRENT store state (e.g. gen-N before its live window)."""
        _git(self.root, "tag", "-f", tag)

    def mark_best_ever(self) -> None:
        _git(self.root, "tag", "-f", "best_ever")

    def rollback_to_best_ever(self) -> str:
        """HARMFUL rail: restore every store from the best_ever tag."""
        _git(self.root, "checkout", "best_ever", "--", ".")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "-m", "rollback to best_ever")
        return _git(self.root, "rev-parse", "best_ever")


class ChangeManifest(BaseModel):
    """A5: the Refiner predicts BEFORE the window; the Verdict falsifies after."""

    model_config = ConfigDict(extra="forbid", strict=False)
    generation: int
    summary: str = Field(min_length=1)
    edited_stores: list[str]
    predicted_fixes: list[str] = Field(default_factory=list)  # archetype/matchup claims
    risk_matchups: list[str] = Field(default_factory=list)


class GenerationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    generation: int
    commit: str
    verdict: GenerationVerdict
    paired_pairs: int
    p_value: float | None = None
    glicko_delta: float | None = None  # None == INCONCLUSIVE under 2*RD (A4)
    rating: float
    rd: float
    power_verdict: str
    rolled_back: bool = False
    manifest_summary: str = ""


Distiller = Callable[[list[Signature], BattleResult], str]
"""Structured signature bullets + result -> <=800-token analysis (A6: never raw text)."""

Refiner = Callable[[HarnessWorkspace, str, int], "ChangeManifest | None"]
"""(workspace, distilled_analysis, generation) -> manifest (None = no edit).
Writes stores in the workspace; MUST return the manifest for its edits."""

BattleRunner = Callable[[Sidecar, str, str, int], Awaitable[BattleResult]]


def default_distiller(signatures: list[Signature], result: BattleResult) -> str:
    """Deterministic formatter (production may swap an LLM role behind the
    same contract — input stays structured-bullets-only)."""
    lines = [f"battle {result.battle_id}: winner={result.winner!r} turns={result.turns}"]
    lines += [f"- {s.signature} x{s.count}: {s.description}" for s in signatures]
    return "\n".join(lines)[:3200]  # ~800 tokens


def team_policy_factory(sidecar: Sidecar, seed: int) -> Policy:
    """CI battler: max-damage play; SKILL comes from the evolving TEAM (the
    one component the workspace provably controls in the house CI lane)."""
    from adx_showdown.bots import max_damage_bot

    return max_damage_bot(sidecar, fallback_seed=seed)


@dataclass
class EvolutionLoop:
    """Generation cycle: window of battles -> distill -> refine (+manifest) ->
    commit/tag -> NEXT window verdicts the edit (CRN pairs vs frozen replica)
    -> HARMFUL rolls back. Frozen replica = the pre-edit team replayed on the
    SAME seeds (common random numbers)."""

    workspace: HarnessWorkspace
    opponent_factory: Callable[[Sidecar, int], Policy]
    events_path: Path
    distiller: Distiller = default_distiller
    refiner: Refiner | None = None
    k_battles: int = 5
    format_id: str = "gen9ou"
    opponent_team: str | None = None
    entrant: str = "house-evolver"
    anchor: str = "anchor-opponent"
    seed_base: int = 50_000
    reports: list[GenerationReport] = field(default_factory=list)

    def _register(self) -> None:
        elog = EventLog(self.events_path)
        if not self.events_path.is_file():
            elog.append("register", {"name": self.entrant})
            elog.append("register", {"name": self.anchor, "frozen": True})

    async def _window(
        self, sidecar: Sidecar, *, team: str, gen: int, label: str
    ) -> list[BattleResult]:
        results = []
        for i in range(self.k_battles):
            seed_val = self.seed_base + gen * 1000 + i  # SAME seeds across teams (CRN)
            results.append(
                await run_battle(
                    sidecar,
                    battle_id=f"{label}-g{gen}-b{i}",
                    format_id=self.format_id,
                    p1_name=self.entrant,
                    p2_name=self.anchor,
                    p1_policy=team_policy_factory(sidecar, seed_val),
                    p2_policy=self.opponent_factory(sidecar, seed_val + 500),
                    seed=[seed_val, 3, 1, 4],
                    p1_team=team,
                    p2_team=self.opponent_team,
                )
            )
        return results

    def _rate(self, results: list[BattleResult], gen: int) -> tuple[float, float, float | None]:
        elog = EventLog(self.events_path)
        before = recompute_ladder(self.events_path).rating(self.entrant)
        elog.append(
            "period",
            {
                "generation": gen,
                "events": [
                    RatingEvent(
                        battle_id=r.battle_id,
                        p1=self.entrant,
                        p2=self.anchor,
                        winner=r.winner,
                        input_log_blake2b16=hashlib.blake2b(
                            "\n".join(r.input_log).encode(), digest_size=16
                        ).hexdigest(),
                    ).model_dump()
                    for r in results
                ],
            },
        )
        after = recompute_ladder(self.events_path).rating(self.entrant)
        return after.rating, after.rd, Ladder.published_delta(before, after)

    async def run_generation(self, sidecar: Sidecar, gen: int) -> GenerationReport:
        """One full cycle. The verdict for generation N's EDIT comes from
        generation N's window — which runs AFTER the edit was committed at
        the END of generation N-1's cycle (next-window falsification)."""
        self._register()
        # pin the state whose team plays THIS window (control lookup target
        # for generation gen+1's falsification)
        self.workspace.tag_state(f"gen-{gen}")
        live_team = self.workspace.team
        manifest = self.workspace.read_manifest()

        results = await self._window(sidecar, team=live_team, gen=gen, label="live")
        rating, rd, delta = self._rate(results, gen)

        verdict: GenerationVerdict = "NEUTRAL"
        p_value: float | None = None
        rolled_back = False
        pairs = 0
        if manifest is not None and manifest.generation == gen:
            # CRN falsification: replay the SAME seeds with the FROZEN
            # (pre-manifest) team = the control replica.
            frozen_team = self._team_at_tag(f"gen-{gen - 1}")
            control = await self._window(sidecar, team=frozen_team, gen=gen, label="frozen")
            paired = [
                (live.winner == self.entrant, ctrl.winner == self.entrant)
                for live, ctrl in zip(results, control, strict=True)
            ]
            pairs = len(paired)
            report = mcnemar_verdict(paired)
            p_value = report.p_value
            verdict = (
                "EFFECTIVE"
                if report.verdict == "EFFECTIVE"
                else "HARMFUL"
                if report.verdict == "HARMFUL"
                else "INCONCLUSIVE"
            )
            if verdict == "HARMFUL":
                self.workspace.rollback_to_best_ever()
                rolled_back = True
            elif verdict == "EFFECTIVE":
                self.workspace.mark_best_ever()

        # distill THIS window, refine for the NEXT generation
        distilled = "\n\n".join(
            self.distiller(extract_signatures(r.key_lines, side="p1"), r) for r in results
        )
        next_manifest: ChangeManifest | None = None
        if self.refiner is not None and not rolled_back:
            next_manifest = self.refiner(self.workspace, distilled, gen + 1)
            if next_manifest is not None:
                self.workspace.write_manifest(next_manifest)
        commit = self.workspace.commit_edits(
            f"edits for generation {gen + 1}"
            + (f": {next_manifest.summary}" if next_manifest else " (none)")
        )

        report_obj = GenerationReport(
            generation=gen,
            commit=commit,
            verdict=verdict,
            paired_pairs=pairs,
            p_value=p_value,
            glicko_delta=delta,
            rating=rating,
            rd=rd,
            power_verdict=window_verdict(abs(delta) if delta else 50.0, battles=self.k_battles),
            rolled_back=rolled_back,
            manifest_summary=manifest.summary if manifest else "",
        )
        self.reports.append(report_obj)
        return report_obj

    def _team_at_tag(self, tag: str) -> str:
        try:
            raw = _git(self.workspace.root, "show", f"{tag}:teams.json")
            return json.loads(raw)["active"]
        except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
            return self.workspace.team

    def evolution_card(
        self, report: GenerationReport, *, parent_lineage_root: str | None
    ) -> EvolutionCard:
        """One generation = one EvolutionCard (A4 receipt)."""
        delta_str = (
            f"glicko_delta={report.glicko_delta:+.1f} (>=2*RD)"
            if report.glicko_delta is not None
            else f"INCONCLUSIVE (<2*RD={2 * report.rd:.0f})"
        )
        seed = Seed(
            kind="team_mutation",
            description=(
                f"gen {report.generation}: {report.manifest_summary or 'no edit'} -> "
                f"{report.verdict} (p={report.p_value}, {delta_str})"
            ),
            evidence_jsonl_excerpt=json.dumps(report.model_dump())[:400],
            confidence="high" if report.verdict in ("EFFECTIVE", "HARMFUL") else "low",
            seed_provenance="learned" if report.verdict == "EFFECTIVE" else "structural",
        )
        return EvolutionCard(
            expedition_id=f"arena-gen-{report.generation}",
            parent_lineage_root=parent_lineage_root,
            winning_pattern=f"rating {report.rating:.0f}±{report.rd:.0f} after gen {report.generation}",
            losing_pattern="rolled back to best_ever" if report.rolled_back else "",
            mutation_seeds={"harness": [seed]},
            boundary_annotations=[f"power={report.power_verdict}", f"verdict={report.verdict}"],
        )
