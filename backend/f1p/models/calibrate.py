"""Fit the simulator's temperature: how much randomness to add around the model's scores.

A small temperature trusts the scores (favourites nearly always win); a large one makes every
race a lottery. We pick the value that maximises the Plackett-Luce likelihood of the actual
finishing orders of held-out races, so the win/podium probabilities match reality.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar

from f1p.models.simulate import plackett_luce_loglik, simulate

T_BOUNDS = (0.05, 50.0)
INCIDENT_RATES = (0.0, 0.02, 0.04, 0.07, 0.1, 0.14, 0.2)
INCIDENT_DROPS = (1.0, 2.0, 3.0, 4.5, 6.0)


def fit_temperature(races: list[tuple[np.ndarray, np.ndarray]], top_k: int | None = None) -> float:
    """``races``: (scores, finishing order of classified drivers as score indices) per race."""
    if not races:
        return 1.0

    def neg_loglik(log_t: float) -> float:
        t = float(np.exp(log_t))
        return -sum(plackett_luce_loglik(s, order, t, top_k) for s, order in races)

    res = minimize_scalar(neg_loglik, bounds=np.log(T_BOUNDS), method="bounded")
    return float(np.exp(res.x))


def position_loglik(
    races: list[tuple[np.ndarray, np.ndarray]],
    temperature: float,
    incident_rate: float,
    incident_drop: float,
    n_sims: int = 3000,
) -> float:
    """Mean log-probability the simulator gave each classified driver's actual finishing place
    (among classified drivers). Counts are smoothed, so a place never simulated isn't -inf."""
    total, count = 0.0, 0
    for scores, order in races:
        m = len(order)
        counts = simulate(
            np.asarray(scores, dtype=float)[order], np.zeros(m), temperature, n_sims,
            seed=0, incident_rate=incident_rate, incident_drop=incident_drop,
        ) * n_sims  # fmt: skip
        probs = (counts + 0.5) / (n_sims + 0.5 * m)
        total += float(np.log(probs[np.arange(m), np.arange(m)]).sum())  # order = actual order
        count += m
    return total / max(count, 1)


def fit_incidents(
    races: list[tuple[np.ndarray, np.ndarray]], temperature: float
) -> tuple[float, float]:
    """How often a driver has a bad day, and how much pace it costs: the pair that best explains
    where held-out drivers actually finished (all places, not just the podium)."""
    if not races:
        return 0.0, 0.0
    best = (position_loglik(races, temperature, 0.0, 0.0), 0.0, 0.0)
    for rate in INCIDENT_RATES[1:]:
        for drop in INCIDENT_DROPS:
            ll = position_loglik(races, temperature, rate, drop)
            if ll > best[0]:
                best = (ll, rate, drop)
    return best[1], best[2]
