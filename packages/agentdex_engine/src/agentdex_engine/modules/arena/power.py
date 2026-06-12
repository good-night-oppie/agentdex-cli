"""Statistical power for battle windows — domain-generic (binary oracle).

The AAOP verdicts doc killed an MVP (Foundry) on exactly this arithmetic;
the arena marks every underpowered window INCONCLUSIVE instead of selling
noise (IDEAL §Arena A4). Generic over any win-probability source so the
same module prices coding-task paired A/Bs (product refutation mitigation).
"""

from __future__ import annotations

import math

_Z = {0.10: 1.6449, 0.05: 1.9600, 0.01: 2.5758}
_ZB = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}


def elo_to_winprob(delta: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-delta / 400.0))


def battles_to_detect(p: float, *, alpha: float = 0.05, power: float = 0.80) -> int:
    """n battles to distinguish win-prob p from 0.5 (two-sided binomial,
    normal approximation). Domain-generic: pass any p, not just Elo."""
    if not 0.0 < p < 1.0 or abs(p - 0.5) < 1e-9:
        return 10**9
    za = _Z.get(round(alpha, 2), 1.96)
    zb = _ZB.get(round(power, 2), 0.8416)
    n = ((za * 0.5 + zb * math.sqrt(p * (1.0 - p))) / abs(p - 0.5)) ** 2
    return math.ceil(n)


def power_table(
    deltas: tuple[float, ...] = (25.0, 50.0, 100.0, 200.0, 400.0),
    *,
    alpha: float = 0.05,
    power: float = 0.80,
) -> dict[float, int]:
    """Elo-delta → battles needed. The ADR-0010 cost table derives from this."""
    return {d: battles_to_detect(elo_to_winprob(d), alpha=alpha, power=power) for d in deltas}


def window_verdict(
    observed_delta: float, battles: int, *, alpha: float = 0.05, power: float = 0.80
) -> str:
    """'POWERED' when the window could have detected the observed delta,
    else 'INCONCLUSIVE' — printed verbatim on receipts (A4)."""
    needed = battles_to_detect(elo_to_winprob(abs(observed_delta)), alpha=alpha, power=power)
    return "POWERED" if battles >= needed else "INCONCLUSIVE"
