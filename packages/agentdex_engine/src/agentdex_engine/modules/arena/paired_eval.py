"""CRN paired lane — same-seed McNemar; the only instrument for small deltas.

Field play cannot afford sub-100-Elo claims (power.py arithmetic); the lab
lane pairs battles on COMMON RANDOM NUMBERS (same seed, same scripted
opponent) and tests discordant pairs. Domain-generic: any paired binary
outcomes work (coding-task A/Bs use the same verdict path).
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict

Verdict = Literal["EFFECTIVE", "HARMFUL", "INCONCLUSIVE"]


class PairedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    pairs: int
    a_only_wins: int  # discordant: A won where B lost (b in McNemar's notation)
    b_only_wins: int
    p_value: float
    verdict: Verdict


def _binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided sign-test p-value under p=0.5."""
    if n == 0:
        return 1.0
    lo = min(k, n - k)
    acc = 0.0
    for i in range(0, lo + 1):
        acc += math.comb(n, i)
    p = 2.0 * acc / (2.0**n)
    return min(1.0, p)


def mcnemar_verdict(outcomes: list[tuple[bool, bool]], *, alpha: float = 0.05) -> PairedReport:
    """outcomes = [(a_win, b_win)] per CRN pair. EFFECTIVE = A beats B."""
    a_only = sum(1 for a, b in outcomes if a and not b)
    b_only = sum(1 for a, b in outcomes if b and not a)
    n = a_only + b_only
    p = _binom_two_sided(a_only, n)
    if p < alpha and a_only > b_only:
        verdict: Verdict = "EFFECTIVE"
    elif p < alpha and b_only > a_only:
        verdict = "HARMFUL"
    else:
        verdict = "INCONCLUSIVE"
    return PairedReport(
        pairs=len(outcomes), a_only_wins=a_only, b_only_wins=b_only, p_value=p, verdict=verdict
    )
