"""team_modes.py — arena-mode → poke-env battle-format + topology substrate
(GA-SELFPLAY-EVOLVE, bene).

The self-play runner (``runner.py``) is ``battle_format``-parameterized but
singles-shaped today (``DEFAULT_FORMAT = gen9randombattle``; the codex decision
prompt says "singles"). The two paid arena modes need more:

  * **team**     — [PAID] two user agents team up → a **doubles** battle topology;
  * **selfplay** — [PAID] self-play-n-self-evolve → self vs self feeding evolution.

This module owns the **substrate mapping** — which poke-env ``battle_format`` and
battle topology each arena mode runs on — which is GA-SELFPLAY-EVOLVE's lane. It
is deliberately distinct from mode *selection / dispatch* (GA-ARENA-MODES,
bene-core): the runner consumes :func:`resolve_format` to know what to spin up.

It is **pure + poke-env-free** (no ``poke_env`` import) so the mode↔format
contract stays importable + testable without the ``selfplay`` extra installed —
the same import-guard discipline the genome/fitness path keeps.

Mode ids match the GA-DESIGN ``data.js`` contract (``solo_bots|pvp|team|selfplay``)
so the design's mode-select cards bind 1:1 to this substrate.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- battle topology -------------------------------------------------------
SINGLES = "singles"  # one active mon per side (the canonical arena format)
DOUBLES = "doubles"  # two active mons per side (team-up / VGC)


@dataclass(frozen=True)
class BattleFormat:
    """A poke-env / Showdown format the arena supports."""

    id: str  # the Showdown format id passed to poke-env, e.g. "gen9randombattle"
    topology: str  # SINGLES | DOUBLES
    team_required: bool  # True → the player brings a team; False → random/auto team


# Supported formats. Singles stays canonical; doubles formats unlock team-up.
# `*random*` formats need no team-builder, so they are the zero-dependency
# defaults for each topology (a real team-builder is a follow-up).
FORMATS: dict[str, BattleFormat] = {
    "gen9randombattle": BattleFormat("gen9randombattle", SINGLES, False),
    "gen9ou": BattleFormat("gen9ou", SINGLES, True),
    "gen9randomdoublesbattle": BattleFormat("gen9randomdoublesbattle", DOUBLES, False),
    "gen9doublesou": BattleFormat("gen9doublesou", DOUBLES, True),
    "gen9vgc2024regh": BattleFormat("gen9vgc2024regh", DOUBLES, True),
}

DEFAULT_SINGLES = "gen9randombattle"
# team-up default = random doubles: a doubles topology with no team-build dep,
# so two agents can team up out of the box (curated team formats are a follow-up).
DEFAULT_TEAM = "gen9randomdoublesbattle"


@dataclass(frozen=True)
class ArenaMode:
    """An arena mode (SPEC §2) and the substrate it runs on."""

    id: str
    paid: bool  # [PAID] modes (team, selfplay) — gated behind membership/invite
    default_format: str
    team_up: bool  # two user agents share one side → requires a DOUBLES format
    self_play: bool  # self vs self, feeding the evolution loop


MODES: dict[str, ArenaMode] = {
    # free
    "solo_bots": ArenaMode("solo_bots", False, DEFAULT_SINGLES, team_up=False, self_play=False),
    "pvp": ArenaMode("pvp", False, DEFAULT_SINGLES, team_up=False, self_play=False),
    # paid
    "team": ArenaMode("team", True, DEFAULT_TEAM, team_up=True, self_play=False),
    "selfplay": ArenaMode("selfplay", True, DEFAULT_SINGLES, team_up=False, self_play=True),
}


class UnknownMode(ValueError):
    """Raised when a mode id is not one of :data:`MODES`."""


class UnsupportedFormat(ValueError):
    """Raised for an unknown format, or one whose topology mismatches the mode."""


def get_mode(mode_id: str) -> ArenaMode:
    try:
        return MODES[mode_id]
    except KeyError:
        raise UnknownMode(f"unknown arena mode {mode_id!r}; known: {sorted(MODES)}") from None


def is_paid(mode_id: str) -> bool:
    """Whether a mode is in the paid set (gated behind membership/invite)."""
    return get_mode(mode_id).paid


def resolve_format(mode_id: str, override: str | None = None) -> BattleFormat:
    """The :class:`BattleFormat` the runner should spin up for ``mode_id``.

    ``override`` (a caller-chosen format) must be a known format AND
    topology-compatible: a ``team_up`` mode requires a **doubles** format, and a
    non-team mode requires a **singles** format — so a team mode can never be
    silently run as singles (which would drop the second agent) or vice-versa.
    """
    mode = get_mode(mode_id)
    fmt_id = override or mode.default_format
    fmt = FORMATS.get(fmt_id)
    if fmt is None:
        raise UnsupportedFormat(f"unknown battle_format {fmt_id!r}; known: {sorted(FORMATS)}")
    want = DOUBLES if mode.team_up else SINGLES
    if fmt.topology != want:
        raise UnsupportedFormat(
            f"mode {mode_id!r} needs a {want} format, but {fmt_id!r} is {fmt.topology}"
        )
    return fmt


__all__ = [
    "SINGLES",
    "DOUBLES",
    "BattleFormat",
    "FORMATS",
    "DEFAULT_SINGLES",
    "DEFAULT_TEAM",
    "ArenaMode",
    "MODES",
    "UnknownMode",
    "UnsupportedFormat",
    "get_mode",
    "is_paid",
    "resolve_format",
]
