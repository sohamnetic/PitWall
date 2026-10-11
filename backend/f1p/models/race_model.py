"""The full predictor: pace ranker + DNF model + calibrated Monte Carlo simulation."""

from __future__ import annotations

import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from f1p import __version__, config
from f1p.features.build import feature_columns
from f1p.models.base import RacePrediction
from f1p.models.calibrate import fit_temperature
from f1p.models.dnf import DnfModel
from f1p.models.ranker import PaceRanker
from f1p.models.simulate import simulate

CALIBRATION_RACES = 30  # held-out recent races used to fit the temperature


class RaceModel:
    def __init__(
        self,
        stage: str,
        name: str | None = None,
        n_sims: int = 10_000,
        temperature_top_k: int | None = 3,
        **ranker_params,
    ):
        self.stage = stage
        self.temperature_top_k = temperature_top_k
        self.name = name or "model"
        self.n_sims = n_sims
        self.ranker_params = ranker_params
        self.features = feature_columns(stage)
        self.temperature = 1.0

    def fit(self, train: pd.DataFrame) -> RaceModel:
        races = train.drop_duplicates("race_id").sort_values("race_idx")["race_idx"]
        # 1. Temperature from out-of-sample scores: train on all but the last N races,
        #    score those N, and fit how much noise matches their real outcomes.
        if len(races) > CALIBRATION_RACES * 3:
            split = races.iloc[-CALIBRATION_RACES]
            early, calib = train[train["race_idx"] < split], train[train["race_idx"] >= split]
            ranker = PaceRanker(self.features, **self.ranker_params).fit(early)
            pairs = _calibration_pairs(ranker, calib)
            self.temperature = fit_temperature(pairs, self.temperature_top_k)
        # 2. Final models on everything.
        self.ranker = PaceRanker(self.features, **self.ranker_params).fit(train)
        self.dnf = DnfModel(self.stage).fit(train)
        return self

    def save(self, path: Path, trained_through: str) -> None:
        self.meta = {
            "stage": self.stage,
            "trained_through": trained_through,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "temperature": self.temperature,
            "version": __version__,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self))

    @staticmethod
    def load(stage: str) -> RaceModel:
        return pickle.loads(model_path(stage).read_bytes())

    def predict_race(self, race: pd.DataFrame) -> RacePrediction:
        scores = self.ranker.score(race)
        p_dnf = self.dnf.predict(race)
        probs = simulate(scores, p_dnf, self.temperature, n_sims=self.n_sims)
        return RacePrediction(
            race["race_id"].iloc[0],
            race["driver_id"].tolist(),
            probs,
            scores=scores,
            p_dnf=p_dnf,
            temperature=self.temperature,
        )


def _calibration_pairs(ranker: PaceRanker, calib: pd.DataFrame):
    pairs = []
    for _, race in calib.groupby("race_id"):
        scores = ranker.score(race)
        finished = race["finish_pos"].to_numpy(dtype=float)
        idx = np.flatnonzero(~np.isnan(finished))
        if len(idx) > 1:
            pairs.append((scores, idx[np.argsort(finished[idx])]))
    return pairs


def model_path(stage: str) -> Path:
    return config.MODELS_DIR / f"race_model_{stage}.pkl"
