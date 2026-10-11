import numpy as np
import pandas as pd
import pytest

from f1p.eval.backtest import walk_forward
from f1p.eval.metrics import calibration_table, race_metrics
from f1p.models.base import RacePrediction, rank_within, sinkhorn
from f1p.models.baselines import RankBaseline, UniformBaseline


def test_sinkhorn_is_doubly_stochastic():
    m = sinkhorn(np.random.default_rng(0).random((6, 6)) + 0.01)
    np.testing.assert_allclose(m.sum(axis=0), 1, atol=1e-6)
    np.testing.assert_allclose(m.sum(axis=1), 1, atol=1e-6)


def test_rank_within_ties_and_nan():
    ranks = rank_within([np.array([0.5, np.nan, 0.5, 0.1]), np.array([2.0, 0.0, 1.0, 9.0])])
    assert ranks.tolist() == [3, 4, 2, 1]


def test_perfect_prediction_metrics():
    n = 5
    pred = RacePrediction("r", list("abcde"), np.eye(n) * 0.999 + 0.001 / n)
    m = race_metrics(pred, np.arange(1, n + 1))
    assert m["spearman"] == pytest.approx(1.0)
    assert m["pos_mae"] == 0 and m["winner_hit"] == 1 and m["top3_hit"] == 1
    assert m["win_logloss"] < 0.01


def test_uniform_win_logloss_is_log_n():
    race = pd.DataFrame({"race_id": "r", "driver_id": list("abcd")})
    pred = UniformBaseline().predict_race(race)
    assert race_metrics(pred, np.array([2, 1, 4, 3]))["win_logloss"] == pytest.approx(np.log(4))


def _synthetic_features(n_races=30, n_drivers=6, noise=0.0, seed=0):
    """Drivers' 'skill' feature predicts the finish, with optional noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(n_races):
        skill = rng.permutation(n_drivers).astype(float)
        finish = np.argsort(np.argsort(skill + rng.normal(0, noise, n_drivers))) + 1
        for d in range(n_drivers):
            rows.append(
                {"race_id": f"2025-{r}", "race_idx": r, "season": 2025 + (r >= 20),
                 "driver_id": f"d{d}", "skill": skill[d], "finish_order": finish[d], "started": 1}
            )  # fmt: skip
    return pd.DataFrame(rows)


def test_rank_baseline_learns_reliability_of_its_rule():
    df = _synthetic_features(noise=0.0)
    b = RankBaseline("skill", lambda r: [r["skill"].to_numpy(dtype=float)])
    b.fit(df[df.race_idx < 20])
    pred = b.predict_race(df[df.race_idx == 25].reset_index(drop=True))
    assert pred.p_win.max() > 0.8  # a perfect rule earns confident probabilities
    np.testing.assert_allclose(pred.probs.sum(axis=0), 1, atol=1e-6)


class SpyPredictor:
    """Records what it was trained on, to check the backtest never trains on the future."""

    name = "spy"

    def __init__(self):
        self.seen = []

    def fit(self, train):
        self.max_idx = train["race_idx"].max()

    def predict_race(self, race):
        self.seen.append((race["race_idx"].iloc[0], self.max_idx))
        return UniformBaseline().predict_race(race)


def test_walk_forward_only_trains_on_the_past():
    df = _synthetic_features()
    spy = SpyPredictor()
    result = walk_forward(df, [spy], test_seasons=[2026])
    assert len(result.races) == 10
    assert all(trained < predicted for predicted, trained in spy.seen)


def test_walk_forward_ranks_good_rule_above_uniform():
    df = _synthetic_features(noise=1.0)
    rule = RankBaseline("skill", lambda r: [r["skill"].to_numpy(dtype=float)])
    s = walk_forward(df, [UniformBaseline(), rule], test_seasons=[2026]).summary()
    assert s.loc["skill", "spearman"] > 0.7
    assert s.loc["skill", "win_logloss"] < s.loc["uniform", "win_logloss"]


def test_calibration_table():
    preds = pd.DataFrame({"p": [0.05, 0.1, 0.9, 0.95], "y": [0, 0, 1, 1]})
    t = calibration_table(preds, "p", "y", bins=2)
    assert t["observed"].tolist() == [0.0, 1.0] and t["n"].tolist() == [2, 2]
