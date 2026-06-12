"""Glicko-2 rating math (Glickman 2022 spec) — pure, dependency-free.

Chosen over Elo because the rating deviation IS the honest error bar the
arena publishes (IDEAL §Arena A4: no delta smaller than 2·RD appears
anywhere). Rating periods map to evolution generations (ADR-0010).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

_SCALE = 173.7178
_TAU = 0.5
_EPS = 1e-6


class Rating(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    rating: float = 1500.0
    rd: float = 350.0
    volatility: float = 0.06
    games: int = 0


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expect(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def update_rating(player: Rating, results: list[tuple[Rating, float]]) -> Rating:
    """One rating-period update. `results` = [(opponent_PRE_period, score)],
    score ∈ {1.0, 0.5, 0.0}. Opponent ratings MUST be pre-period snapshots
    (Glicko-2 spec) — the Ladder enforces this."""
    mu = (player.rating - 1500.0) / _SCALE
    phi = player.rd / _SCALE
    sigma = player.volatility
    if not results:
        phi_star = math.sqrt(phi * phi + sigma * sigma)
        return Rating(
            rating=player.rating,
            rd=min(phi_star * _SCALE, 350.0),
            volatility=sigma,
            games=player.games,
        )

    inv_v = 0.0
    delta_sum = 0.0
    for opp, score in results:
        mu_j = (opp.rating - 1500.0) / _SCALE
        phi_j = opp.rd / _SCALE
        e = _expect(mu, mu_j, phi_j)
        g_j = _g(phi_j)
        inv_v += g_j * g_j * e * (1.0 - e)
        delta_sum += g_j * (score - e)
    v = 1.0 / inv_v
    delta = v * delta_sum

    # volatility update (Illinois-style iteration on f)
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (_TAU * _TAU)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * _TAU) < 0:
            k += 1
        big_b = a - k * _TAU
    fa, fb = f(big_a), f(big_b)
    while abs(big_b - big_a) > _EPS:
        big_c = big_a + (big_a - big_b) * fa / (fb - fa)
        fc = f(big_c)
        if fc * fb <= 0:
            big_a, fa = big_b, fb
        else:
            fa = fa / 2.0
        big_b, fb = big_c, fc
    sigma_new = math.exp(big_a / 2.0)

    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * delta_sum
    return Rating(
        rating=mu_new * _SCALE + 1500.0,
        rd=phi_new * _SCALE,
        volatility=sigma_new,
        games=player.games + len(results),
    )
