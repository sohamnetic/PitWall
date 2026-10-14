"""Simple rule-based predictors every real model must beat.

Each baseline orders the field by a rule (e.g. grid position). To turn that order into
probabilities fairly, it learns from earlier races how often predicted rank r actually
finished in position p, then balances that table for the current field size.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from f1p.models.base import RacePrediction, actual_rank, rank_within, sinkhorn

MAX_FIELD = 30
SMOOTHING = 0.5  # pseudo-count added to every (rank, position) cell

KeyFn = Callable[[pd.DataFrame], list[np.ndarray]]


def _col(race: pd.DataFrame, name: str) -> np.ndarray:
    return race[name].to_numpy(dtype=float)


def _team_strength(race: pd.DataFrame) -> np.ndarray:
    """Team form in the current regulation era, falling back to all-time form."""
    return race["team_era_form"].fillna(race["team_form"]).to_numpy(dtype=float)


class RankBaseline:
    """Order drivers by ``key_fn`` and map ranks to probabilities learned from history."""

    def __init__(self, name: str, key_fn: KeyFn):
        self.name = name
        self.key_fn = key_fn
        self.counts = np.full((MAX_FIELD, MAX_FIELD), SMOOTHING)

    def ranks(self, race: pd.DataFrame) -> np.ndarray:
        return rank_within(self.key_fn(race))

    def fit(self, train: pd.DataFrame) -> None:
        counts = np.full((MAX_FIELD, MAX_FIELD), SMOOTHING)
        for _, race in train.groupby("race_id", sort=False):
            pred, act = self.ranks(race), actual_rank(race)
            np.add.at(counts, (pred - 1, act - 1), 1)
        self.counts = counts

    def predict_race(self, race: pd.DataFrame) -> RacePrediction:
        n = len(race)
        ranks = self.ranks(race)
        probs = sinkhorn(self.counts[ranks - 1][:, :n])
        return RacePrediction(race["race_id"].iloc[0], race["driver_id"].tolist(), probs)


class UniformBaseline:
    """Every driver equally likely to finish anywhere: the 'knows nothing' reference."""

    name = "uniform"

    def fit(self, train: pd.DataFrame) -> None:
        pass

    def predict_race(self, race: pd.DataFrame) -> RacePrediction:
        n = len(race)
        return RacePrediction(
            race["race_id"].iloc[0], race["driver_id"].tolist(), np.full((n, n), 1 / n)
        )


def grid_baseline() -> RankBaseline:
    """Finish = starting grid (pit-lane starters at the back)."""
    return RankBaseline(
        "grid",
        lambda r: [_col(r, "grid_pct"), _col(r, "quali_pos_pct"), _col(r, "drv_form")],
    )


def championship_baseline() -> RankBaseline:
    """Finish = current championship order (round 1: last season's form)."""
    return RankBaseline("championship", lambda r: [_col(r, "champ_rank_pct"), _col(r, "drv_form")])


def last_race_baseline() -> RankBaseline:
    """Finish = order of the previous race."""
    return RankBaseline("last_race", lambda r: [_col(r, "drv_last_pos_pct"), _col(r, "drv_form")])


def team_form_baseline() -> RankBaseline:
    """Finish = recent car pace order, teammates split by driver form."""
    return RankBaseline("team_form", lambda r: [_team_strength(r), _col(r, "drv_form")])


def practice_baseline() -> RankBaseline:
    """Finish = fastest practice lap order (falls back to team form without lap data)."""
    return RankBaseline(
        "practice",
        lambda r: [_col(r, "fp_best_gap_pct"), _team_strength(r), _col(r, "drv_form")],
    )


def baselines_for(stage: str) -> list:
    pre = [
        UniformBaseline(),
        championship_baseline(),
        last_race_baseline(),
        team_form_baseline(),
        practice_baseline(),
    ]
    return pre if stage == "pre" else [*pre, grid_baseline()]
