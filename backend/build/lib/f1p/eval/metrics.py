"""Scoring a race prediction against what happened.

Ordering metrics judge the predicted finishing order; probability metrics judge how
well-calibrated the win / podium / points probabilities are (lower Brier and log-loss = better).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from f1p.config import POINTS_POSITIONS
from f1p.models.base import RacePrediction

EPS = 1e-6

# Metrics where a higher number is better; everything else is lower-is-better.
HIGHER_IS_BETTER = {"spearman", "winner_hit", "top3_hit", "top10_hit"}


def _binary_logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def race_metrics(pred: RacePrediction, actual: np.ndarray) -> dict[str, float]:
    """``actual`` is the true finishing rank 1..n of each driver, in ``pred.driver_ids`` order."""
    pr = pred.pred_rank
    win, podium, points = actual == 1, actual <= 3, actual <= POINTS_POSITIONS

    def topk_hit(k: int) -> float:
        return len(set(np.flatnonzero(pr <= k)) & set(np.flatnonzero(actual <= k))) / k

    return {
        "spearman": float(spearmanr(pr, actual).statistic),
        "pos_mae": float(np.abs(pr - actual).mean()),
        "winner_hit": float(pr[win][0] == 1),
        "top3_hit": topk_hit(3),
        "top10_hit": topk_hit(POINTS_POSITIONS),
        "win_logloss": float(-np.log(max(pred.p_win[win][0], EPS))),
        "win_brier": float(((pred.p_win - win) ** 2).sum()),
        "podium_logloss": _binary_logloss(pred.p_podium, podium),
        "podium_brier": float(((pred.p_podium - podium) ** 2).mean()),
        "points_logloss": _binary_logloss(pred.p_points, points),
        "points_brier": float(((pred.p_points - points) ** 2).mean()),
        # Probability given to each driver's exact finishing place: punishes "impossible" 0%s.
        "pos_logloss": float(
            -np.log(np.maximum(pred.probs[np.arange(len(actual)), actual - 1], EPS)).mean()
        ),
    }


def calibration_table(
    preds: pd.DataFrame, prob_col: str, outcome_col: str, bins: int = 10
) -> pd.DataFrame:
    """Reliability table: mean predicted probability vs observed frequency per bin."""
    edges = np.linspace(0, 1, bins + 1)
    b = pd.cut(preds[prob_col], edges, include_lowest=True)
    out = preds.groupby(b, observed=True).agg(
        predicted=(prob_col, "mean"), observed=(outcome_col, "mean"), n=(outcome_col, "size")
    )
    return out.reset_index(names="bin")
