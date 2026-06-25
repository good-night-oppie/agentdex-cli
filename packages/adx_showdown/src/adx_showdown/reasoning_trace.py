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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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

    @classmethod
    def from_capture(cls, cap: dict[str, Any]) -> ReasoningTrace:
        """Build a trace from an explain-capture dict (``arena2d_explain_battle/1`` —
        the shape ``codex_decide_explain`` + the capture harness produce). Abstain/error
        rows (no ``move``) are dropped — they are not decisions."""
        decisions: list[Decision] = []
        seq = 0
        for t in cap.get("turns", []):
            move = str(t.get("move") or "").strip()
            if not move:
                continue
            decisions.append(
                Decision(
                    seq=seq,
                    turn=int(t.get("turn") or 0),
                    side="p1",
                    active=str(t.get("active_species") or ""),
                    opponent=str(t.get("opponent_species") or ""),
                    move=move,
                    rationale=str(t.get("rationale") or ""),
                    considered=[
                        ConsideredMove(
                            move=str(c.get("move") or ""), why_not=str(c.get("why_not") or "")
                        )
                        for c in (t.get("considered") or [])
                        if str(c.get("move") or "").strip()
                    ],
                )
            )
            seq += 1
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


__all__ = [
    "SCHEMA_VERSION",
    "ConsideredMove",
    "Decision",
    "BattleResultSummary",
    "ReasoningTrace",
]
