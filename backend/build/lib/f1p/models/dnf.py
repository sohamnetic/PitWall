"""Probability that each driver fails to finish (crash, mechanical failure, ...).

Retirements are mostly luck. In walk-forward tests a gradient-boosted model did worse than
just predicting the average DNF rate (it overfit noise), so this is a small, regularised
logistic regression on a handful of features with a plausible causal link.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from f1p.models.ranker import recency_weights


def dnf_features(rows: pd.DataFrame, stage: str) -> pd.DataFrame:
    x = pd.DataFrame(
        {
            "team_dnf_rate": rows["team_dnf_rate"],
            "drv_dnf_rate": rows["drv_dnf_rate"],
            "street": (rows["circuit_type"] == "street").astype(float),
            "rain": rows["wx_rain_frac"].fillna(0.0),
            "new_team_in_era": (rows["team_era_races"] < 5).astype(float),
        },
        index=rows.index,
    )
    if stage == "post":
        # Back-markers get caught in more first-lap incidents.
        x["grid_pct"] = rows["grid_pct"].fillna(0.5)
        x["pitlane_start"] = rows["pitlane_start"].fillna(0.0)
    return x


class DnfModel:
    def __init__(self, stage: str, c: float = 1.0):
        self.stage = stage
        self.model = LogisticRegression(C=c, max_iter=1000)
        self.constant: float | None = None

    def fit(self, train: pd.DataFrame) -> DnfModel:
        rows = train[train["dnf"].notna()]
        y = rows["dnf"].astype(int)
        if y.nunique() < 2:  # e.g. no retirements in the data at all: use the plain rate
            self.constant = float(y.mean()) if len(y) else 0.1
            return self
        self.constant = None
        self.model.fit(dnf_features(rows, self.stage), y, sample_weight=recency_weights(rows))
        return self

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        if self.constant is not None:
            return np.full(len(rows), self.constant)
        return self.model.predict_proba(dnf_features(rows, self.stage))[:, 1]
