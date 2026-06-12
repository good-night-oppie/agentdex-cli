"""Arena measurement instrument (ADR-0010 phase 5) — A4/A8 anchors in code."""

from agentdex_engine.modules.arena.events import ChainError, EventLog, recompute_ladder
from agentdex_engine.modules.arena.glicko import Rating, update_rating
from agentdex_engine.modules.arena.ladder import InvalidRatingEvent, Ladder, RatingEvent
from agentdex_engine.modules.arena.paired_eval import PairedReport, mcnemar_verdict
from agentdex_engine.modules.arena.power import (
    battles_to_detect,
    elo_to_winprob,
    power_table,
    window_verdict,
)
from agentdex_engine.modules.arena.signatures import Signature, extract_signatures, load_patterns

__all__ = [
    "ChainError",
    "EventLog",
    "InvalidRatingEvent",
    "Ladder",
    "PairedReport",
    "Rating",
    "RatingEvent",
    "Signature",
    "battles_to_detect",
    "elo_to_winprob",
    "extract_signatures",
    "load_patterns",
    "mcnemar_verdict",
    "power_table",
    "recompute_ladder",
    "update_rating",
    "window_verdict",
]
