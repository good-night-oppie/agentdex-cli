"""Curated gen9 OU starter pack + team validation helpers (F3).

`pokemon-showdown generate-team gen9ou` DOES NOT EXIST (measured — gen9ou has
no team generator), and the OU banlist drifts under model weights (Volcarona
is Uber now). So: ~12 curated teams in export format, CI-validated against the
PINNED pokemon-showdown version; visiting agents draft 1-of-3 from this pack
and evolve by MUTATION, never composition from a blank page (ADR-0010 F3).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from adx_showdown.sidecar import Sidecar

TEAMS_DIR = Path(__file__).resolve().parent / "teams"
DEFAULT_FORMAT = "gen9ou"


class TeamValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    name: str
    packed: str
    valid: bool
    errors: list[str] = Field(default_factory=list)


def starter_pack() -> dict[str, str]:
    """Return {team_name: export_text} for every committed starter team."""
    teams: dict[str, str] = {}
    for path in sorted(TEAMS_DIR.glob("*.txt")):
        teams[path.stem] = path.read_text(encoding="utf-8")
    return teams


async def pack_team(sidecar: Sidecar, export_text: str) -> str:
    """Export text → packed format (server-side, never trusts client packing)."""
    resp = await sidecar.request("pack-team", **{"export": export_text})
    return str(resp["packed"])


async def validate_team(
    sidecar: Sidecar, packed: str, *, format_id: str = DEFAULT_FORMAT
) -> tuple[bool, list[str]]:
    """Validate a packed team; returns (valid, structured_errors).

    The error list is the visitor-facing repair signal: each entry names the
    offending set, so a mutating agent can fix one slot at a time.
    """
    resp = await sidecar.request("validate-team", format=format_id, team=packed)
    return bool(resp["valid"]), [str(e) for e in resp.get("errors", [])]


async def validate_starter_pack(
    sidecar: Sidecar, *, format_id: str = DEFAULT_FORMAT
) -> list[TeamValidation]:
    """Pack + validate every starter team (the CI criterion for F3)."""
    results: list[TeamValidation] = []
    for name, export_text in starter_pack().items():
        packed = await pack_team(sidecar, export_text)
        valid, errors = await validate_team(sidecar, packed, format_id=format_id)
        results.append(TeamValidation(name=name, packed=packed, valid=valid, errors=errors))
    return results
