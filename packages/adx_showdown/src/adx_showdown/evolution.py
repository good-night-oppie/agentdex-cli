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
import logging
import subprocess
import tempfile
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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

log = logging.getLogger(__name__)

STORE_FILES = ("prompt.md", "subagents.json", "skills.json", "memory.json", "teams.json")
GenerationVerdict = Literal["EFFECTIVE", "NEUTRAL", "HARMFUL", "INCONCLUSIVE"]

# Observability for the "load-bearing surface": which of the 5 stores does the
# battle path actually READ? Today only teams.json is read on the behavioral
# path (the battler reads no store; the loop reads workspace.team -> teams.json);
# prompt.md/subagents.json/skills.json/memory.json are written + committed but
# never read, so edits to them are inert and unmeasurable by the falsification
# rail. This tracer turns that fact into a test-asserted, RED-on-regression
# invariant — and means that when a store is wired into the policy, its reads
# WILL show up here. ALL behavioral store reads must go through
# HarnessWorkspace.read_store so the trace stays honest.
_STORE_READS: ContextVar[Counter[str] | None] = ContextVar("_store_reads", default=None)


@contextmanager
def trace_store_reads() -> Iterator[Counter[str]]:
    """Record each HarnessWorkspace.read_store call within the block.

    Returns a Counter keyed by store filename; stores never read register as 0
    (Counter semantics). Reentrancy-safe via a ContextVar token (propagates into
    the async run_generation since it runs in the same task)."""
    counter: Counter[str] = Counter()
    token = _STORE_READS.set(counter)
    try:
        yield counter
    finally:
        _STORE_READS.reset(token)


class EvolutionStateError(RuntimeError):
    """Corrupt run state detected (e.g. a change_manifest left on disk for the
    wrong generation). Raised rather than silently skipping the falsification
    window — a silent skip is exactly the P0 failure mode this guards."""


def _git(workspace: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


# Sentinel delta used for the POWERED/INCONCLUSIVE power check when NO glicko
# delta was measured (the <2*RD case, glicko_delta is None). It asks "had this
# window enough battles to detect even a sizeable ~50-Elo move?".
_MISSING_DELTA_SENTINEL = 50.0


def _power_input_delta(glicko_delta: float | None) -> float:
    """Delta fed to ``window_verdict`` for the POWERED/INCONCLUSIVE check.

    A genuine *measured* delta of ``0.0`` must pass through as ``0.0`` — equal
    teams mean no finite window can "power" a detection of difference, so the
    verdict is correctly INCONCLUSIVE. Only a *missing* measurement
    (``glicko_delta is None``) falls back to ``_MISSING_DELTA_SENTINEL``.

    The earlier expression ``abs(delta) if delta else 50.0`` treated a real
    ``0.0`` as falsy and fabricated a 50-Elo move, reporting a made-up POWERED
    verdict for a window that measured exactly no difference (P0 silent-failure
    bug). The ``is not None`` guard is the fix (mirrors the correct guard already
    used when rendering ``glicko_delta`` on the EvolutionCard).
    """
    return abs(glicko_delta) if glicko_delta is not None else _MISSING_DELTA_SENTINEL


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

    def read_store(self, name: str) -> str:
        """Read a store file's text, recording the read under any active
        trace_store_reads context. EVERY behavioral store read must go through
        here so the load-bearing surface stays observable (store_shas is exempt:
        it is integrity hashing, not behavioral consumption)."""
        reads = _STORE_READS.get()
        if reads is not None:
            reads[name] += 1
        return (self.root / name).read_text()

    @property
    def team(self) -> str:
        return json.loads(self.read_store("teams.json"))["active"]

    @property
    def system_prompt(self) -> str:
        """The Refiner-evolved prompt.md, read on the BEHAVIORAL path.

        Parallel to :pyattr:`team`: a single behavioral read of an evolution
        store, routed through :meth:`read_store` so it registers in
        ``trace_store_reads``. Wiring this into the entrant policy
        (:func:`prompt_steered_policy_factory`) is what turns prompt.md from an
        inert, unmeasurable store into a load-bearing one the falsification rail
        can finally measure (the gap flagged in the STORE_FILES note above)."""
        return self.read_store("prompt.md")

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

    def clear_manifest(self) -> None:
        """Remove the consumed manifest from the working tree.

        The manifest is a SINGLE-USE pending prediction: written at the END of
        generation N (targeting N+1) and consumed by generation N+1's
        falsification check. Leaving it on disk afterward is the P0 leak — a
        None-return Refiner at the next generation lets the stale manifest
        linger, the `generation == gen` guard then silently goes False, no
        falsification window runs, and the loop reports NEUTRAL forever.

        CRITICAL TIMING (PR #155 review #3418161864 + #3418161865): clearing is
        DEFERRED to generation completion — called only after the verdict is
        about to be durably committed, and only when no NEW manifest replaced it.
        If the window/refiner/verdict step raises before then, the manifest stays
        on disk so a retry re-runs the required falsification instead of silently
        skipping it. The wrong-generation guard likewise raises with the manifest
        still present, preserving the evidence for the operator.
        """
        (self.root / "change_manifest.json").unlink(missing_ok=True)

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
        # A rollback discards the pending prediction too. best_ever's restored
        # tree can carry a stale change_manifest.json that would otherwise trip
        # the wrong-generation guard at the next run_generation (false
        # EvolutionStateError). Clear it so rollback lands a clean state.
        (self.root / "change_manifest.json").unlink(missing_ok=True)
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
    pr_url: str | None = None  # set when a pr_publisher opened a GitHub PR for this gen


Distiller = Callable[[list[Signature], BattleResult], str]
"""Structured signature bullets + result -> <=800-token analysis (A6: never raw text)."""

Refiner = Callable[[HarnessWorkspace, str, int], "ChangeManifest | None"]
"""(workspace, distilled_analysis, generation) -> manifest (None = no edit).
Writes stores in the workspace; MUST return the manifest for its edits."""

BattleRunner = Callable[[Sidecar, str, str, int], Awaitable[BattleResult]]

PrPublisher = Callable[[HarnessWorkspace, "GenerationReport", EvolutionCard], "str | None"]
"""(workspace, report, card) -> PR url (or None if skipped/not configured).

Closes the meta-harness loop through git: a generation's measured outcome is
committed + opened as a GitHub PR for review. Injected like ``refiner`` so CI /
tests stay fully offline (default None = no publish); only production passes a
real publisher (e.g. ``gh_pr_publisher``). A publish fault must never abort the
falsification loop — the caller catches + logs."""


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


# prompt.md -> behavior. The entrant policy is steered by a directive parsed from
# the Refiner-evolved prompt.md, so editing prompt.md now MOVES the battle outcome
# — the edit the falsification rail can finally measure. Default ("house battler
# v0") maps to max_damage, so existing house-lane behavior is unchanged; only a
# Refiner that writes a strategy keyword changes play. (Production can instead
# inject an LLM `entrant_factory` that threads ws.system_prompt verbatim into the
# model's system prompt — the same seam, with the real LLM consumer.)
_STRATEGY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trickroom", ("trick room", "trickroom")),
    ("stall", ("defens", "stall", "status", "recover", "passive", "tank")),
    ("offense", ("aggress", "offens", "hyper", "sweep", "setup", "attack")),
    ("balance", ("balance", "pivot", "hazard")),
)


def select_strategy(system_prompt: str) -> str:
    """Map a system prompt to an entrant archetype (pure, deterministic).

    The FIRST keyword group that matches wins (tuple order = priority); no match
    falls back to ``max_damage``. This is the house-lane consumer of prompt.md —
    it MUST change with the prompt for the store to be load-bearing, which is
    exactly what the load-bearing smoke falsifies."""
    low = system_prompt.lower()
    for strategy, keywords in _STRATEGY_KEYWORDS:
        if any(kw in low for kw in keywords):
            return strategy
    return "max_damage"


def _bot_for(strategy: str) -> Callable[..., Policy]:
    from adx_showdown.bots import (
        balance_bot,
        hyper_offense_bot,
        max_damage_bot,
        stall_bot,
        trick_room_bot,
    )

    return {
        "offense": hyper_offense_bot,
        "stall": stall_bot,
        "balance": balance_bot,
        "trickroom": trick_room_bot,
        "max_damage": max_damage_bot,
    }[strategy]


def prompt_steered_policy_factory(
    workspace: HarnessWorkspace, sidecar: Sidecar, seed: int
) -> Policy:
    """House entrant policy STEERED by ``workspace.system_prompt`` (prompt.md).

    Reads prompt.md on the behavioral path (so it registers in
    ``trace_store_reads``) and dispatches to the archetype the prompt selects.
    Same opponent + same seed, two prompt.md variants -> different battle
    behavior: that delta is the proof prompt.md is no longer inert. Team SKILL
    still also flows from the evolving teams.json."""
    strategy = select_strategy(workspace.system_prompt)
    return _bot_for(strategy)(sidecar, fallback_seed=seed)


EntrantFactory = Callable[[HarnessWorkspace, Sidecar, int], Policy]
"""(workspace, sidecar, seed) -> entrant Policy. Workspace-aware so the entrant
can read evolving stores (prompt.md via system_prompt); injectable so production
can swap an LLM-backed entrant that threads ws.system_prompt into the model."""


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
    # Workspace-aware entrant: reads prompt.md (system_prompt) so the evolved
    # prompt is load-bearing. Defaults to the house prompt-steered bot; production
    # can inject an LLM entrant that threads ws.system_prompt into the model.
    entrant_factory: EntrantFactory = prompt_steered_policy_factory
    refiner: Refiner | None = None
    pr_publisher: PrPublisher | None = None
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
                    p1_policy=self.entrant_factory(self.workspace, sidecar, seed_val),
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

    def _quarantine_window(self, results: list[BattleResult]) -> None:
        """Quarantine every battle in a rolled-back (HARMFUL) window so its
        already-appended RatingEvents stop counting toward the published ladder.

        `_rate` appends the window's RatingEvents to the period log before the
        verdict is known; a HARMFUL git rollback restores the stores but leaves
        those events in place. recompute_ladder pre-scans for `quarantine`
        events and filters matching battle_ids out of every period, so emitting
        one `quarantine` event per battle_id reverts the ladder impact without
        rewriting history (the period event stays, truthfully recording that the
        battles happened; the quarantine records that they were voided)."""
        elog = EventLog(self.events_path)
        for r in results:
            elog.append("quarantine", {"battle_id": r.battle_id})

    def _harmful_refresh(self) -> tuple[float, float, float | None]:
        """Report values for a rolled-back (HARMFUL) window, read AFTER
        `_quarantine_window`. rating/rd come from the POST-quarantine ladder so
        the GenerationReport + the A4 receipt match what `/ladder` now publishes
        (it excludes the voided window); the move delta is ALWAYS None — a
        voided window sells no move.

        The delta is unconditionally None, NOT `published_delta(pre_window,
        post)`. A generation that fails after `_rate` appended the live period
        but before the verdict is retried, and the retry reuses the
        deterministic `live-g{gen}-b{i}` battle_ids — so `_rate` appends a
        SECOND period with the SAME ids and the quarantine voids them across
        BOTH periods (recompute_ladder filters battle_ids globally). `post`
        therefore reverts PAST the retry's pre-window baseline (back to before
        the abandoned attempt), and `published_delta(pre_window, post)` would
        advertise a spurious positive move on a rolled-back report — the exact
        A4 lie the quarantine exists to prevent (PR #159 review #3422007501)."""
        post = recompute_ladder(self.events_path).rating(self.entrant)
        return post.rating, post.rd, None

    async def run_generation(self, sidecar: Sidecar, gen: int) -> GenerationReport:
        """One full cycle. The verdict for generation N's EDIT comes from
        generation N's window — which runs AFTER the edit was committed at
        the END of generation N-1's cycle (next-window falsification)."""
        self._register()
        # pin the state whose team plays THIS window (control lookup target
        # for generation gen+1's falsification)
        self.workspace.tag_state(f"gen-{gen}")
        live_team = self.workspace.team
        # READ (do NOT delete yet) the single-use pending manifest. Deletion is
        # deferred to generation completion (clear_manifest below) so any failure
        # in the window/verdict path leaves the manifest on disk for a clean
        # retry instead of silently dropping the falsification. A present
        # manifest MUST target THIS generation; a wrong-generation manifest is
        # corrupt run state (crash mid-write / manual edit / a rollback that
        # failed to clear) and is raised — with the manifest STILL PRESENT so the
        # evidence survives for the operator (PR #155 reviews #3418161864/65).
        manifest = self.workspace.read_manifest()
        if manifest is not None and manifest.generation != gen:
            raise EvolutionStateError(
                f"change_manifest targets generation {manifest.generation} but generation "
                f"{gen} is starting — a manifest is single-use and must be consumed by the "
                f"generation it targets. This is corrupt run state, not a recoverable skip."
            )

        results = await self._window(sidecar, team=live_team, gen=gen, label="live")
        rating, rd, delta = self._rate(results, gen)

        verdict: GenerationVerdict = "NEUTRAL"
        p_value: float | None = None
        rolled_back = False
        pairs = 0
        if manifest is not None:
            # manifest.generation == gen is now an invariant (the mismatch
            # raised above), so a present manifest always falsifies THIS gen.
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
                # _rate already appended this live window's RatingEvents to the
                # period log BEFORE the verdict was known. The git rollback
                # restores the STORES but never touches events.jsonl, so without
                # this the reverted team's losses stay baked into
                # recompute_ladder — the published rating + the A4 receipt would
                # advertise a team that was rolled back. Quarantine every
                # battle_id in the rolled-back window; recompute_ladder filters
                # them out of the period (events.py pre-scan + period filter).
                self._quarantine_window(results)
                # Refresh the reported rating/rd from the POST-quarantine ladder
                # and void the move delta — see _harmful_refresh. _rate computed
                # the stale values from the pre-quarantine period; leaving them
                # would re-introduce the receipt-vs-ladder divergence the
                # quarantine removes, just moved into the report fields (PR #158
                # review #3421911866 + PR #159 review #3422007501).
                rating, rd, delta = self._harmful_refresh()
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
        # Clear the consumed manifest ONLY now (post-verdict, pre-commit) and
        # ONLY when no new manifest replaced it. Deferring to here means a
        # failure anywhere in the window/verdict/refiner path above left the
        # manifest on disk for a clean retry; a non-None refiner already
        # overwrote it with the next prediction (PR #155 reviews
        # #3418161864/#3418161865). The unlink + the new write are both captured
        # by commit_edits's `git add -A`, recording the state atomically.
        if next_manifest is None:
            self.workspace.clear_manifest()
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
            power_verdict=window_verdict(_power_input_delta(delta), battles=self.k_battles),
            rolled_back=rolled_back,
            manifest_summary=manifest.summary if manifest else "",
        )
        self.reports.append(report_obj)

        # Closed-loop GitHub publish: open/refresh a PR carrying this generation's
        # EvolutionCard + evolved team + verdict. Cadence gate — only on a MEASURED
        # move (verdict != NEUTRAL) or a rollback; NEUTRAL gens have no measured
        # edit and would be PR noise. A publish fault is a side-channel failure:
        # log and continue so the falsification loop + run state are never aborted
        # by a flaky network / gh / remote.
        if self.pr_publisher is not None and (verdict != "NEUTRAL" or rolled_back):
            try:
                card = self.evolution_card(report_obj, parent_lineage_root=None)
                report_obj.pr_url = self.pr_publisher(self.workspace, report_obj, card)
            except Exception:
                log.warning("evolution PR publish failed for gen %s", gen, exc_info=True)

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


# --------------------------------------------------------------------------- #
# Closed-loop GitHub publisher (the operator-facing PrPublisher implementation)
# --------------------------------------------------------------------------- #


def _pr_body(report: GenerationReport, card: EvolutionCard) -> str:
    """Human-reviewable PR body: the measured outcome + the EvolutionCard."""
    return "\n".join(
        [
            f"## Evolution generation {report.generation} — **{report.verdict}**",
            "",
            f"- rating: {report.rating:.0f} ± {report.rd:.0f}",
            f"- glicko_delta: {report.glicko_delta}",
            f"- McNemar p_value: {report.p_value} (paired_pairs={report.paired_pairs})",
            f"- power_verdict: {report.power_verdict}",
            f"- rolled_back: {report.rolled_back}",
            f"- edit: {report.manifest_summary or '(none)'}",
            "",
            "EvolutionCard (`evolution_card.json`) + evolved `teams.json` are in this branch.",
            "",
            "🤖 closed evolution meta-harness loop (agentdex)",
        ]
    )


def gh_pr_publisher(
    repo: str,
    *,
    base: str = "main",
    remote: str = "origin",
    remote_url: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> PrPublisher:
    """Build a :data:`PrPublisher` that commits the EvolutionCard onto the
    measured ``gen-{N}`` snapshot, pushes the generation as a branch to ``repo``,
    and opens a GitHub PR via the ambient ``gh`` CLI (fleet auth /
    ``GITHUB_TOKEN``).

    ``repo`` = ``owner/name``. ``remote_url`` defaults to the repo's https URL.
    ``runner`` is injectable for tests. The target repo should be seeded once from
    a ``gen-0`` push so each generation's PR diff is just that generation's change.
    Network / push / gh failures raise; :meth:`EvolutionLoop.run_generation`
    catches + logs (publish is a side-channel, never a loop abort).
    """
    url = remote_url or f"https://github.com/{repo}.git"

    def publish(ws: HarnessWorkspace, report: GenerationReport, card: EvolutionCard) -> str | None:
        branch = f"evolution/gen-{report.generation}-{report.verdict.lower()}"
        snapshot_ref = f"gen-{report.generation}"
        _git(ws.root, "rev-parse", "--verify", snapshot_ref)

        with tempfile.TemporaryDirectory(prefix="adx-evolution-pr-") as tmp:
            publish_root = Path(tmp) / "publish"
            _git(ws.root, "worktree", "add", "-B", branch, str(publish_root), snapshot_ref)
            try:
                # Card artifact alongside the measured evolved stores. This
                # happens in an isolated publish worktree so the authoritative
                # harness workspace does not advance on publish-only failures.
                (publish_root / "evolution_card.json").write_text(
                    card.model_dump_json(indent=1) + "\n"
                )
                _git(publish_root, "add", "-A")
                _git(
                    publish_root,
                    "commit",
                    "-q",
                    "--allow-empty",
                    "-m",
                    f"evolution gen {report.generation}: {report.verdict}",
                )
                try:
                    _git(publish_root, "remote", "add", remote, url)
                except subprocess.CalledProcessError:
                    _git(publish_root, "remote", "set-url", remote, url)
                _git(publish_root, "push", "-f", remote, branch)

                try:
                    existing = runner(
                        [
                            "gh",
                            "pr",
                            "view",
                            "--repo",
                            repo,
                            "--head",
                            branch,
                            "--json",
                            "url",
                            "--jq",
                            ".url",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    existing_url = (getattr(existing, "stdout", "") or "").strip()
                    if existing_url:
                        return existing_url
                except subprocess.CalledProcessError:
                    pass

                result = runner(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        repo,
                        "--head",
                        branch,
                        "--base",
                        base,
                        "--title",
                        f"evolution gen {report.generation}: {report.verdict}",
                        "--body",
                        _pr_body(report, card),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            finally:
                _git(ws.root, "worktree", "remove", "--force", str(publish_root))
        return (getattr(result, "stdout", "") or "").strip() or None

    return publish
