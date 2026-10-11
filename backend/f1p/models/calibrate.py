"""Fit the simulator's temperature: how much randomness to add around the model's scores.

A small temperature trusts the scores (favourites nearly always win); a large one makes every
race a lottery. We pick the value that maximises the Plackett-Luce likelihood of the actual
finishing orders of held-out races, so the win/podium probabilities match reality.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar

from f1p.models.simulate import plackett_luce_loglik

T_BOUNDS = (0.05, 50.0)


def fit_temperature(races: list[tuple[np.ndarray, np.ndarray]], top_k: int | None = None) -> float:
    """``races``: (scores, finishing order of classified drivers as score indices) per race."""
    if not races:
        return 1.0

    def neg_loglik(log_t: float) -> float:
        t = float(np.exp(log_t))
        return -sum(plackett_luce_loglik(s, order, t, top_k) for s, order in races)

    res = minimize_scalar(neg_loglik, bounds=np.log(T_BOUNDS), method="bounded")
    return float(np.exp(res.x))
