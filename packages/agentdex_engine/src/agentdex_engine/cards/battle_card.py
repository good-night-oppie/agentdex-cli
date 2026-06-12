"""BattleCard — the arena's per-battle receipt (ADR-0010 phase 4).

A battle is an expedition variant; this card is the battle-specific artifact
that rides NEXT TO the ResultCard (which carries pass_rate/cost/speed for the
Pareto pool). Strict + extra="forbid" per Three Cards doctrine.

IDEAL_EXPERIENCE §Arena A2: a rating event without a re-simulable inputLog is
rejected — `input_log_path` is therefore required, and `input_log_blake2b16`
pins the artifact so a receipt can be verified byte-for-byte (A8).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BattleCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    battle_id: str = Field(min_length=1)
    expedition_id: str = Field(min_length=1)
    format_id: str = Field(min_length=1)  # e.g. "gen9ou", "gen9randombattle"
    seed: list[int] = Field(min_length=4, max_length=4)
    p1_name: str = Field(min_length=1)  # sanitized upstream (protocol boundary)
    p2_name: str = Field(min_length=1)
    winner: str  # sanitized; "" == tie
    turns: int = Field(ge=0)
    input_log_path: str = Field(min_length=1)  # A2: re-simulable artifact
    input_log_blake2b16: str = Field(pattern=r"^[0-9a-f]{32}$")
    # harness identity: blake2b-16 of the packed team (None = generated team,
    # derivable from seed). Phase 7 extends this to the full 5-store SHA set.
    p1_team_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    p2_team_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    # Glicko fields are None until the phase-5 ladder rates the battle; a
    # published delta smaller than 2*RD never appears anywhere (A4).
    rating_before: float | None = None
    rating_after: float | None = None
    rating_deviation: float | None = Field(default=None, ge=0.0)
    duration_sec: float = Field(ge=0.0)
    decision_tokens: int = Field(ge=0)  # LLM cost basis; 0 for scripted bots
    choice_errors: int = Field(ge=0, default=0)
