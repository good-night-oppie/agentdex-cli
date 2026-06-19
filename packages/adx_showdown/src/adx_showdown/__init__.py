"""adx_showdown — Pokémon Showdown battle substrate (ADR-0010 phase 3).

Surface:
- :class:`adx_showdown.sidecar.Sidecar` — persistent Node BattleStream
  multiplexer (NDJSON/stdio), the ONLY simulation surface (F1).
- :mod:`adx_showdown.protocol` — |request| parsing + the A6 sanitizer boundary.
- :mod:`adx_showdown.lineproto` — typed |TYPE|args battle line-protocol (P1-a):
  the single wire format every renderer (TUI/web/replay) folds over.
- :mod:`adx_showdown.client` — the state reducer (P1-b): folds the protocol
  stream into one queryable :class:`~adx_showdown.client.BattleState`.
- :mod:`adx_showdown.sim` — lockstep battle driver + inputLog re-simulation (A2).
- :mod:`adx_showdown.teams` — curated CI-validated gen9 OU starter pack (F3).
- :mod:`adx_showdown.harness` — BattleHarness genome (self-play meta-harness
  Contract 1): the unit bene mutates; resolved to a sim Policy by A1.
"""

from adx_showdown.client import (
    BattleClient,
    BattleState,
    SideState,
    reduce,
    reduce_lines,
)
from adx_showdown.harness import (
    KNOWN_STRATEGIES,
    BattleHarness,
    ToolPolicy,
    seed_harness,
)
from adx_showdown.lineproto import (
    MESSAGE_TYPES,
    NONDETERMINISTIC_TYPES,
    PokemonIdent,
    ProtocolEvent,
    Tier,
    parse_line,
    parse_stream,
    strip_nondeterministic,
    tier_of,
)
from adx_showdown.protocol import parse_request, sanitize_name
from adx_showdown.sidecar import Sidecar, SidecarError, sidecar_available
from adx_showdown.sim import (
    BattleResult,
    canonical_protocol,
    events,
    replay_input_log,
    run_battle,
)

__all__ = [
    "KNOWN_STRATEGIES",
    "MESSAGE_TYPES",
    "NONDETERMINISTIC_TYPES",
    "BattleClient",
    "BattleHarness",
    "BattleResult",
    "BattleState",
    "ToolPolicy",
    "seed_harness",
    "PokemonIdent",
    "SideState",
    "reduce",
    "reduce_lines",
    "ProtocolEvent",
    "Sidecar",
    "SidecarError",
    "Tier",
    "canonical_protocol",
    "events",
    "parse_line",
    "parse_request",
    "parse_stream",
    "replay_input_log",
    "run_battle",
    "sanitize_name",
    "sidecar_available",
    "strip_nondeterministic",
    "tier_of",
]
