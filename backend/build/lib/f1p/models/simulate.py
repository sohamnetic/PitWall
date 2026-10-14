"""Monte Carlo race simulator.

Each simulated race:
1. every driver retires with their own probability ``p_dnf``;
2. some drivers have a bad day without retiring (first-lap damage, a penalty, a slow stop):
   with probability ``incident_rate`` they lose a random amount of pace;
3. the remaining drivers finish in a Plackett-Luce order: the winner is drawn with probability
   proportional to ``exp(score / T)``, then second from those left, and so on;
4. retirements fill the last places.

Plackett-Luce sampling is done with the Gumbel-max trick: sorting ``score / T + Gumbel noise``
gives exactly a Plackett-Luce draw, so thousands of races take a few milliseconds.
"""

from __future__ import annotations

import numpy as np

from f1p.config import N_SIMULATIONS


def simulate_races(
    scores: np.ndarray,
    p_dnf: np.ndarray,
    temperature: float,
    n_sims: int = N_SIMULATIONS,
    seed: int | None = 0,
    incident_rate: float = 0.0,
    incident_drop: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulated races: ``finish[s, i]`` = 0-based position of driver i in race s, and
    ``retired[s, i]`` = whether driver i retired in race s."""
    rng = np.random.default_rng(seed)
    scores = np.asarray(scores, dtype=float)
    n = len(scores)
    keys = scores / temperature + rng.gumbel(size=(n_sims, n))
    retired = rng.random((n_sims, n)) < np.asarray(p_dnf, dtype=float)
    if incident_rate > 0:
        # Gumbel noise has a thin lower tail: on its own a front-runner who doesn't retire
        # almost never finishes ninth. A bad day knocks off an exponential amount of pace.
        # (Drawn after the retirements, so incident_rate=0 reproduces older snapshots.)
        hit = rng.random((n_sims, n)) < incident_rate
        keys = keys - hit * rng.exponential(incident_drop, size=(n_sims, n))
    keys = np.where(retired, keys - 1e6, keys)  # retirements sort behind every finisher
    finish = np.argsort(np.argsort(-keys, axis=1), axis=1)
    return finish, retired


def position_probs(finish: np.ndarray) -> np.ndarray:
    """``probs[i, j]`` = share of simulations where driver i finished position j + 1."""
    n_sims, n = finish.shape
    probs = np.zeros((n, n))
    np.add.at(probs, (np.broadcast_to(np.arange(n), finish.shape), finish), 1.0)
    return probs / n_sims


def simulate(
    scores: np.ndarray,
    p_dnf: np.ndarray,
    temperature: float,
    n_sims: int = N_SIMULATIONS,
    seed: int | None = 0,
    incident_rate: float = 0.0,
    incident_drop: float = 0.0,
) -> np.ndarray:
    """Return ``probs[i, j]`` = share of simulations where driver i finished position j + 1."""
    finish, _ = simulate_races(
        scores, p_dnf, temperature, n_sims, seed, incident_rate, incident_drop
    )
    return position_probs(finish)


def plackett_luce_loglik(
    scores: np.ndarray, order: np.ndarray, temperature: float, top_k: int | None = None
) -> float:
    """Log-likelihood of an observed finishing order under Plackett-Luce.

    ``order`` lists driver indices from winner to last (classified finishers only). With
    ``top_k``, only the first ``top_k`` picks count ("who won, then who was second among the
    rest, ..."), focusing on the front of the field.
    """
    s = np.asarray(scores, dtype=float)[order] / temperature
    # log P = sum_k [ s_k - logsumexp(s_k..s_end) ]
    tail_lse = np.logaddexp.accumulate(s[::-1])[::-1]
    terms = s - tail_lse
    return float(terms[:top_k].sum())
