"""ReasoningTrace — the per-battle agent-reasoning document arena2d renders.

DDIA document model: one battle is a self-contained aggregate read together (the
Showdown ``log`` + the ordered ``decisions``), with no cross-battle joins on the read
path — so it is one document per battle, not a relational spread. Two design rails carry
the rest:

- **Source vs derived boundary (the arena2d honesty contract).** This document holds
  ONLY source-of-truth, attested fields: the protocol ``log`` and, per decision, the
  chosen ``move`` + verbatim ``rationale`` (``codex_decide``) + the ``considered`` fan
  the policy actually weighed and rejected (``codex_decide_explain``, PR #610).
  Type-effectiveness ×scores and PRIMITIVE labels (PUNISH / PIVOT / …) are DERIVED
  client-side by ``dex.js`` and are deliberately NOT stored here — deriving them on read
  keeps the source small and stops the UI from claiming the agent computed a score it
  never emitted.
- **One schema, two transports.** The static ``web/arena2d/data.js`` is the
  ``file://``-safe PROJECTION of this same document (``to_data_js_projection``); a future
  ``GET …/trace`` endpoint serves the full ``ReasoningTrace``. A finished battle's trace
  is immutable, so the endpoint is trivially edge-cacheable (ETag = battle_id+schema,
  ``Cache-Control: immutable``) — no invalidation problem (DDIA Ch.5 derived data).

The producer is the only writer, so the models are strict (``extra='forbid'``); evolution
is additive behind ``schema_version`` (schema-on-read tolerance lives on the consumer).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _slug(s: Any) -> str:
    """Alphanumeric-only lowercase id (matches arena2d's anim.js ``slug``), so a chosen
    move ``stoneedge`` aligns to the log's ``Stone Edge`` and a switch ``zamazentacrowned``
    to ``Zamazenta-Crowned``."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


SCHEMA_VERSION = "reasoning_trace/1"


class ConsideredMove(BaseModel):
    """One attested rejected candidate: a legal action the policy weighed but did not
    pick, with its (<=8-word) reason. Sanitized upstream by ``_clean_considered`` —
    only legal, non-chosen ids reach here, so the fan never misrepresents the choice."""

    model_config = ConfigDict(extra="forbid")

    move: str = Field(min_length=1)
    why_not: str = ""


class Decision(BaseModel):
    """One p1 decision on the action stream. ``move`` + ``rationale`` + ``considered``
    are REAL (codex output); ``active``/``opponent`` are the revealed context at decision
    time (forward-only, no future leakage)."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)  # 0-based order on the p1 action stream (pairs to the log)
    turn: int = Field(default=0, ge=0)  # battle turn (0 when the capture didn't carry it)
    side: Literal["p1", "p2"] = "p1"
    active: str = ""  # our active species at the moment of choosing
    opponent: str = ""  # opponent active species (revealed only)
    move: str = Field(min_length=1)
    rationale: str = ""
    considered: list[ConsideredMove] = Field(default_factory=list)


class BattleResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: Literal["p1", "p2", "tie", "unknown"] = "unknown"
    turns: int = Field(default=0, ge=0)


class ReasoningTrace(BaseModel):
    """The full per-battle document. ``log`` + ``decisions`` are the source of truth."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reasoning_trace/1"] = SCHEMA_VERSION
    battle_id: str = ""
    battle_format: str = "gen9randombattle"
    result: BattleResultSummary = Field(default_factory=BattleResultSummary)
    log: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)

    def to_data_js_projection(self) -> dict[str, Any]:
        """The arena2d ``data.js`` projection: ``{LOG, RATIONALES}``, where each
        RATIONALES entry is ``{move, rationale[, considered]}``. A strict SUBSET of this
        document, so the static fixture and the live endpoint share one schema — the
        viewer's static fallback is byte-compatible with what the endpoint would serve."""
        rationales: list[dict[str, Any]] = []
        for d in self.decisions:
            entry: dict[str, Any] = {"move": d.move, "rationale": d.rationale}
            if d.considered:
                entry["considered"] = [{"move": c.move, "why_not": c.why_not} for c in d.considered]
            rationales.append(entry)
        return {"LOG": list(self.log), "RATIONALES": rationales}

    @staticmethod
    def _executed_p1_actions(log: list[str]) -> list[tuple[str, int]]:
        """The p1 actions the log actually EXECUTED, in order, as ``(slug, turn)``.

        Mirrors arena2d's anim.js decision rule so the trace's decisions correspond 1:1
        to what happened, not to every capture row: a ``|move|p1…`` is always a decision;
        a ``|switch|p1…`` is a decision only AFTER the first ``|turn|`` (the pre-turn
        switch is the lead) and only when it is a real ``switch`` — a ``|drag|`` is a
        forced phaze, not an agent choice. ``turn`` is the enclosing ``|turn|N``."""
        out: list[tuple[str, int]] = []
        started = False
        cur_turn = 0
        for line in log:
            p = line.split("|")
            tag = p[1] if len(p) > 1 else ""
            if tag == "turn":
                started = True
                try:
                    cur_turn = int(p[2])
                except (ValueError, IndexError):
                    pass
            elif tag == "move" and len(p) > 3 and p[2].startswith("p1"):
                out.append((_slug(p[3]), cur_turn))
            elif tag == "switch" and len(p) > 3 and p[2].startswith("p1") and started:
                out.append((_slug(p[3].split(",")[0]), cur_turn))
        return out

    @classmethod
    def from_capture(cls, cap: dict[str, Any]) -> ReasoningTrace:
        """Build a trace from an explain-capture dict (``arena2d_explain_battle/1`` —
        the shape ``codex_decide_explain`` + the capture harness produce).

        Decisions are ALIGNED to the executed p1 actions in the log, not promoted from
        every capture row: the capture stream carries retries / un-executed deliberations
        (e.g. a choice computed for a turn that never resolved), so a blind 1-row-per-rich
        loop would put a phantom decision in the immutable trace (review #3473480421).
        Each executed action greedily consumes the next capture row whose chosen move
        slug-matches it; capture rows that never execute are dropped, and ``turn`` comes
        from the log (the capture itself does not carry it). Abstain/error rows (no
        ``move``) are skipped before matching."""
        rows = [t for t in cap.get("turns", []) if str(t.get("move") or "").strip()]
        executed = cls._executed_p1_actions(list(cap.get("log") or []))
        decisions: list[Decision] = []
        ri = 0  # capture-row pointer (greedy, in order)
        for slug, turn in executed:
            # find the next unconsumed capture row whose chosen move matches this action
            match = None
            for j in range(ri, len(rows)):
                if _slug(rows[j].get("move")) == slug:
                    match, ri = rows[j], j + 1
                    break
            if match is None:
                continue  # executed action with no captured rationale — omit (no fabrication)
            decisions.append(
                Decision(
                    seq=len(decisions),
                    turn=turn,
                    side="p1",
                    active=str(match.get("active_species") or ""),
                    opponent=str(match.get("opponent_species") or ""),
                    move=str(match.get("move") or "").strip(),
                    rationale=str(match.get("rationale") or ""),
                    considered=[
                        ConsideredMove(
                            move=str(c.get("move") or ""), why_not=str(c.get("why_not") or "")
                        )
                        for c in (match.get("considered") or [])
                        if str(c.get("move") or "").strip()
                    ],
                )
            )
        res = cap.get("result", {}) or {}
        winner = res.get("winner")
        return cls(
            battle_id=str(cap.get("battle_tag") or ""),
            battle_format=str(cap.get("battle_format") or "gen9randombattle"),
            result=BattleResultSummary(
                winner=winner if winner in ("p1", "p2", "tie") else "unknown",
                turns=int(res.get("turns") or 0),
            ),
            log=list(cap.get("log") or []),
            decisions=decisions,
        )

    def _players_from_log(self) -> list[str]:
        """Display names from the ``|player|pN|name|…`` protocol lines, p1 then p2 —
        the Showdown replay ``players`` field. Missing slots fall back to ``p1``/``p2``."""
        names: dict[str, str] = {}
        for line in self.log:
            parts = line.split("|")
            if len(parts) >= 4 and parts[1] == "player" and parts[2] in ("p1", "p2"):
                names[parts[2]] = parts[3] or parts[2]
        return [names.get("p1", "p1"), names.get("p2", "p2")]

    def _format_display(self) -> str:
        """The human format from the ``|tier|`` line (e.g. ``[Gen 9] Random Battle``),
        falling back to the format id — mirrors Showdown's ``format`` (display) vs
        ``formatid`` (id) split."""
        for line in self.log:
            parts = line.split("|")
            if len(parts) >= 3 and parts[1] == "tier":
                return parts[2]
        return self.battle_format

    def to_ps_replay(self, *, uploadtime: int | None = None) -> dict[str, Any]:
        """A Pokémon-Showdown-replay-shaped REST projection (the
        ``replay.pokemonshowdown.com/<id>.json`` convention): a flat document whose
        ``log`` is the raw protocol as ONE newline-joined STRING, plus ``id`` /
        ``format`` / ``formatid`` / ``players`` / ``uploadtime``. Existing PS replay
        tooling can read those base fields unchanged.

        The agent's reasoning rides as ADDITIVE, namespaced extension fields —
        ``decisions`` (per-decision rationale + the attested ``considered`` fan) and
        ``schema`` — so a PS-shaped consumer ignores them and an agentdex consumer reads
        them. This is the shape a ``GET …/<id>.json`` endpoint serves; a finished
        battle is immutable, so it is trivially cacheable (ETag = id+schema)."""
        return {
            "id": self.battle_id,
            "format": self._format_display(),
            "formatid": self.battle_format,
            "players": self._players_from_log(),
            "uploadtime": uploadtime,
            "log": "\n".join(self.log),
            # agentdex extension (additive; PS-shaped readers ignore these):
            "schema": self.schema_version,
            "result": self.result.model_dump(),
            "decisions": [d.model_dump() for d in self.decisions],
        }


__all__ = [
    "SCHEMA_VERSION",
    "ConsideredMove",
    "Decision",
    "BattleResultSummary",
    "ReasoningTrace",
]
