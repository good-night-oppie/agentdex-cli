"""adx_showdown — Pokémon Showdown battle substrate (ADR-0010 phase 3).

Surface:
- :class:`adx_showdown.sidecar.Sidecar` — persistent Node BattleStream
  multiplexer (NDJSON/stdio), the ONLY simulation surface (F1).
- :mod:`adx_showdown.protocol` — |request| parsing + the A6 sanitizer boundary.
- :mod:`adx_showdown.sim` — lockstep battle driver + inputLog re-simulation (A2).
- :mod:`adx_showdown.teams` — curated CI-validated gen9 OU starter pack (F3).
"""

from adx_showdown.protocol import parse_request, sanitize_name
from adx_showdown.sidecar import Sidecar, SidecarError, sidecar_available
from adx_showdown.sim import BattleResult, replay_input_log, run_battle

__all__ = [
    "BattleResult",
    "Sidecar",
    "SidecarError",
    "parse_request",
    "replay_input_log",
    "run_battle",
    "sanitize_name",
    "sidecar_available",
]
