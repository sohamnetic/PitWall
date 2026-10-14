"""Walk-forward backtest: for each race in order, train on everything before it, predict it.

The feature matrix is already point-in-time (see ``tests/test_features.py``), and training
rows are restricted to races strictly before the one being predicted, so no result is ever
seen before it happened.

Non-starters (withdrawn before the race) are dropped from both training and evaluation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd

from f1p.eval.metrics import HIGHER_IS_BETTER, race_metrics
from f1p.models.base import Predictor, actual_rank

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    races: pd.DataFrame  # one row per (model, race) with metrics
    drivers: pd.DataFrame  # one row per (model, race, driver) with probabilities + outcomes

    def summary(self, by: tuple[str, ...] = ("model",)) -> pd.DataFrame:
        metric_cols = [c for c in self.races.columns if c not in ("model", "race_id", "season")]
        out = self.races.groupby(list(by))[metric_cols].mean()
        out.insert(0, "races", self.races.groupby(list(by)).size())
        return out


def walk_forward(
    features: pd.DataFrame,
    predictors: list[Predictor],
    test_seasons: list[int],
    refit_every: int = 1,
) -> BacktestResult:
    df = features[features["started"] == 1].copy()
    test = (
        df[df["season"].isin(test_seasons) & df["finish_order"].notna()]
        .groupby("race_id")["race_idx"]
        .first()
        .sort_values()
    )
    race_rows, driver_rows = [], []
    start = time.perf_counter()
    for i, (race_id, idx) in enumerate(test.items()):
        race = df[df["race_id"] == race_id].reset_index(drop=True)
        train = df[(df["race_idx"] < idx) & df["finish_order"].notna()]
        actual = actual_rank(race)
        for p in predictors:
            if i % refit_every == 0:
                p.fit(train)
            pred = p.predict_race(race)
            race_rows.append(
                {"model": p.name, "race_id": race_id, "season": int(race["season"].iloc[0]),
                 **race_metrics(pred, actual)}
            )  # fmt: skip
            frame = pred.to_frame().assign(model=p.name, actual_rank=actual)
            driver_rows.append(frame)
        if (i + 1) % 20 == 0:
            log.info("%d/%d races (%.0fs)", i + 1, len(test), time.perf_counter() - start)

    drivers = pd.concat(driver_rows, ignore_index=True)
    drivers["won"] = (drivers["actual_rank"] == 1).astype(float)
    drivers["podium"] = (drivers["actual_rank"] <= 3).astype(float)
    drivers["in_points"] = (drivers["actual_rank"] <= 10).astype(float)
    return BacktestResult(races=pd.DataFrame(race_rows), drivers=drivers)


def best_by_metric(summary: pd.DataFrame) -> pd.Series:
    """Which model wins each metric."""
    return pd.Series(
        {
            m: (summary[m].idxmax() if m in HIGHER_IS_BETTER else summary[m].idxmin())
            for m in summary.columns
            if m != "races"
        }
    )
