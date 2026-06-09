"""Per-model rate-table loader for bridges that surface tokens but not
dollars (PR-W, closes DEFERRED "Real cost 端到端" — partial; manus codex-
web fallback still uses the heuristic when it lacks token surface).

Used by codex_bridge to derive a cost_dollar from tokens × per-model
rate at result-frame time. Cached at module load.

Schema is in rate_table.yaml; see header there for drift policy.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_TABLE_PATH = Path(__file__).parent / "rate_table.yaml"


@lru_cache(maxsize=1)
def _load_table() -> dict[str, dict[str, Any]]:
    if not _TABLE_PATH.is_file():
        return {}
    try:
        body = yaml.safe_load(_TABLE_PATH.read_text())
        return body or {}
    except (yaml.YAMLError, OSError):
        return {}


def _resolve_rate(model_id: str | None) -> dict[str, float] | None:
    """Return the rate row for ``model_id`` or the codex-default fallback."""
    table = _load_table()
    if not table:
        return None
    if model_id and model_id in table:
        return table[model_id]
    # Prefix match (e.g. `gpt-4o-2024-08-06` → `gpt-4o`).
    if model_id:
        candidates = sorted(
            (k for k in table if model_id.startswith(k) and k != "codex-default"),
            key=len,
            reverse=True,
        )
        if candidates:
            return table[candidates[0]]
    return table.get("codex-default")


def estimate_cost_usd(
    model_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float | None:
    """Return ``input × in_rate + output × out_rate + cached × cached_rate``
    in USD. None when the table is empty or no rate row matched.
    """
    rate = _resolve_rate(model_id)
    if rate is None:
        return None
    try:
        in_rate = float(rate.get("input_usd_per_1m", 0.0))
        out_rate = float(rate.get("output_usd_per_1m", 0.0))
        cached_rate = float(rate.get("cached_usd_per_1m", in_rate))
    except (TypeError, ValueError):
        return None
    total = (
        (input_tokens * in_rate) + (output_tokens * out_rate) + (cached_tokens * cached_rate)
    ) / 1_000_000.0
    return round(max(total, 0.0), 6)


__all__ = ["estimate_cost_usd"]
