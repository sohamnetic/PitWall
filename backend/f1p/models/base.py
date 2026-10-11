"""Common prediction format shared by baselines, ML models and the simulator.

Every predictor outputs, for one race, a matrix ``probs[i, j]`` = P(driver i finishes in
position j + 1). Rows sum to 1 (each driver finishes somewhere) and columns sum to 1 (each
position is taken by someone). Win / podium / points probabilities and expected position are
all read off this matrix, so every model is scored the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from f1p.config import POINTS_POSITIONS


@dataclass
class RacePrediction:
    race_id: str
    driver_ids: list[str]
    probs: np.ndarray  # (n_drivers, n_positions)
    # Simulation inputs, when the prediction came from the race simulator. Stored with
    # snapshots so questions ("will A beat B?") can be answered from fresh simulations.
    scores: np.ndarray | None = None
    p_dnf: np.ndarray | None = None
    temperature: float | None = None

    @property
    def p_win(self) -> np.ndarray:
        return self.probs[:, 0]

    @property
    def p_podium(self) -> np.ndarray:
        return self.probs[:, :3].sum(axis=1)

    @property
    def p_points(self) -> np.ndarray:
        return self.probs[:, :POINTS_POSITIONS].sum(axis=1)

    @property
    def expected_pos(self) -> np.ndarray:
        return self.probs @ np.arange(1, self.probs.shape[1] + 1)

    @property
    def pred_rank(self) -> np.ndarray:
        """Predicted finishing order 1..n (by expected position, ties by win probability)."""
        order = np.lexsort((-self.p_win, self.expected_pos))
        ranks = np.empty(len(order), dtype=int)
        ranks[order] = np.arange(1, len(order) + 1)
        return ranks

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "race_id": self.race_id,
                "driver_id": self.driver_ids,
                "pred_rank": self.pred_rank,
                "expected_pos": self.expected_pos,
                "p_win": self.p_win,
                "p_podium": self.p_podium,
                "p_points": self.p_points,
            }
        )


class Predictor(Protocol):
    name: str

    def fit(self, train: pd.DataFrame) -> None:
        """Learn from rows of earlier races (features + targets)."""

    def predict_race(self, race: pd.DataFrame) -> RacePrediction:
        """Predict one race from its feature rows (one per driver)."""


def sinkhorn(m: np.ndarray, iters: int = 200, tol: float = 1e-9) -> np.ndarray:
    """Scale a positive square matrix until rows and columns all sum to 1."""
    m = np.asarray(m, dtype=float).copy()
    for _ in range(iters):
        m /= m.sum(axis=1, keepdims=True)
        m /= m.sum(axis=0, keepdims=True)
        if np.abs(m.sum(axis=1) - 1).max() < tol:
            break
    return m


def rank_within(values: list[np.ndarray]) -> np.ndarray:
    """Ranks 1..n by lexicographic order of the given keys (first key most important).

    Lower values rank first; NaN sorts last.
    """
    keys = [np.where(np.isnan(v), np.inf, v) for v in reversed(values)]
    order = np.lexsort(keys)
    ranks = np.empty(len(order), dtype=int)
    ranks[order] = np.arange(1, len(order) + 1)
    return ranks


def actual_rank(race: pd.DataFrame) -> np.ndarray:
    """Actual finishing order 1..n among the race's rows (DNFs at their sheet position)."""
    return rank_within([race["finish_order"].to_numpy(dtype=float)])
