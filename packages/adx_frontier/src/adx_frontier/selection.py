"""Constrained-Pareto, objective-ordered winner selection over frontier axes.

Owns the Pareto semantics that callers (``adx run``, ladders) reuse: map
interview objective tokens → ``FRONTIER_AXES``, prune hard cost constraints,
drop dominated records, then lexicographically order survivors by the user's
priority. Pure stdlib; no I/O.
"""

from __future__ import annotations

from adx_frontier.candidate import FRONTIER_AXES
from adx_frontier.ledger import FrontierRecord, dominates

OBJECTIVE_AXIS_MAP: dict[str, str] = {
    "correctness": "quality",
    "quality": "quality",
    "cost": "cost_dollar",
    "cost_dollar": "cost_dollar",
    "latency": "wall_clock_sec",
    "wall_clock_sec": "wall_clock_sec",
    "speed": "wall_clock_sec",
}


def objective_axes(objective: list[str]) -> list[str]:
    """Map interview objective tokens (most-important-first) to frontier axes.

    Unknown tokens are skipped. Axes not mentioned are appended in
    ``FRONTIER_AXES`` order so ordering is always total. Returns a list of
    unique axis names. Empty ``objective`` yields ``list(FRONTIER_AXES)``.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for token in objective:
        axis = OBJECTIVE_AXIS_MAP.get(token)
        if axis is None or axis in seen:
            continue
        seen.add(axis)
        ordered.append(axis)
    for axis in FRONTIER_AXES:
        if axis not in seen:
            ordered.append(axis)
    return ordered


def ordering_key(scores: dict[str, float], axes: list[str]) -> tuple:
    """Lexicographic sort key for ``axes`` priority order.

    Negate ``quality`` (higher better); use raw ``cost_dollar`` /
    ``wall_clock_sec`` (lower better).
    """
    key: list[float] = []
    for axis in axes:
        value = float(scores[axis])
        if axis == "quality":
            key.append(-value)
        else:
            key.append(value)
    return tuple(key)


def select(
    records: list[FrontierRecord],
    objective: list[str],
    *,
    max_cost_dollar: float | None = None,
) -> list[FrontierRecord]:
    """Constrained-Pareto objective-ordered selection.

    1. Drop records with ``scores["cost_dollar"] > max_cost_dollar`` (when set).
    2. Drop dominated records (via ``dominates``; records assumed same partition).
    3. Sort survivors by ``ordering_key(objective_axes(objective))``;
       tie-break lastly on ``record.candidate`` for determinism.

    Returns the ordered survivor list (winner first). Empty input → ``[]``.
    """
    if not records:
        return []
    candidates = list(records)
    if max_cost_dollar is not None:
        candidates = [r for r in candidates if r.scores["cost_dollar"] <= max_cost_dollar]
    if not candidates:
        return []
    non_dominated = [
        record for record in candidates if not any(dominates(other, record) for other in candidates)
    ]
    axes = objective_axes(objective)
    return sorted(
        non_dominated,
        key=lambda r: (*ordering_key(r.scores, axes), r.candidate),
    )
