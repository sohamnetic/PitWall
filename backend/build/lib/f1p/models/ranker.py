"""LightGBM LambdaRank model scoring each driver's race pace (higher score = finishes ahead).

Trained on classified finishers only: retirements are handled by the separate DNF model, so
the ranker learns "how fast is this driver/car this weekend" without crash noise.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from f1p import config

RANKER_PARAMS = dict(
    objective="lambdarank",
    n_estimators=300,
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=40,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    verbose=-1,
)


def recency_weights(train: pd.DataFrame) -> np.ndarray:
    """Exponential decay by races-ago, with a boost for the newest regulation era."""
    latest = train["race_idx"].max()
    age = latest - train["race_idx"].to_numpy()
    w = 0.5 ** (age / config.SAMPLE_WEIGHT_HALF_LIFE_RACES)
    newest_era = config.regulation_era(int(train["season"].max()))
    in_era = train["season"].map(config.regulation_era).to_numpy() == newest_era
    return w * np.where(in_era, config.CURRENT_ERA_WEIGHT_BOOST, 1.0)


GAINS = {
    # Every position matters equally: learns the whole finishing order.
    "linear": list(range(64)),
    # Front-heavy (LightGBM default): learns who wins and makes the podium.
    "exp": [2**i - 1 for i in range(31)],
}


class PaceRanker:
    """One LambdaRank model per gain scheme; scores are standardised and averaged."""

    def __init__(self, features: list[str], gains: tuple[str, ...] = ("linear", "exp"), **params):
        self.features = features
        self.gains = gains
        self.params = {**RANKER_PARAMS, **params}
        self.models: list[lgb.LGBMRanker] = []

    def fit(self, train: pd.DataFrame) -> PaceRanker:
        cls = train[train["finish_pos"].notna()].sort_values(["race_idx", "finish_pos"])
        n_cls = cls.groupby("race_id")["finish_pos"].transform("count")
        relevance = (n_cls - cls["finish_pos"]).clip(lower=0).astype(int)
        groups = cls.groupby("race_idx", sort=True).size().to_numpy()
        weights = recency_weights(cls)
        self.models, self.scales = [], []
        for gain in self.gains:
            # Exponential gains overflow above ~30 levels; cap labels to the top 30.
            rel = relevance if gain == "linear" else relevance - (n_cls - 30).clip(lower=0)
            params = {**self.params, "label_gain": GAINS[gain]}
            model = lgb.LGBMRanker(**params).fit(
                cls[self.features], rel.clip(lower=0), group=groups, sample_weight=weights
            )
            self.models.append(model)
            # One fixed scale per model (spread within training races), so a race with a
            # dominant favourite keeps its wider score gap.
            pred = pd.Series(model.predict(cls[self.features]), index=cls.index)
            self.scales.append(float(pred.groupby(cls["race_idx"]).std().mean()) + 1e-9)
        return self

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        total = np.zeros(len(rows))
        for model, scale in zip(self.models, self.scales, strict=True):
            s = model.predict(rows[self.features])
            total += (s - s.mean()) / scale
        return total / len(self.models)

    def importance(self) -> pd.Series:
        gain = sum(m.booster_.feature_importance("gain") for m in self.models)
        return pd.Series(gain / gain.sum(), index=self.features).sort_values(ascending=False)
