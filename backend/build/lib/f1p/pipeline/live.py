"""Live operation: predict an upcoming race, save a snapshot, score it after the race.

Every prediction is built "as of" its stage cutoff (``truncate_to``) with a model trained only
on races before it, so predictions made after the fact (backfills) are still honest. They are
flagged ``made_before_cutoff = False`` so the track record can separate them out.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import Engine, select

from f1p import __version__
from f1p.data.db import get_engine, get_session
from f1p.data.models import Prediction, PredictionRow, PredictionScore
from f1p.eval.metrics import race_metrics
from f1p.features.build import build_features
from f1p.features.tables import Stage, Tables, cutoff, load_tables, truncate_to
from f1p.models.base import RacePrediction, rank_within, sinkhorn
from f1p.models.baselines import championship_baseline, grid_baseline
from f1p.models.race_model import RaceModel, model_path

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _race_start(races: pd.DataFrame) -> pd.Series:
    return races["race_start_utc"].fillna(pd.to_datetime(races["race_date"]))


def resolve_race(t: Tables, spec: str, now: datetime) -> str:
    """'next' = first race not yet finished; 'last' = most recent race with a result."""
    finished = set(t.results.loc[t.results["session"] == "R", "race_id"])
    races = t.races.sort_values("race_idx")
    if spec == "next":
        upcoming = races[
            ~races["id"].isin(finished) & (_race_start(races) > now - pd.Timedelta(hours=3))
        ]
        if upcoming.empty:
            raise ValueError("No upcoming race in the calendar.")
        return upcoming["id"].iloc[0]
    if spec == "last":
        done = races[races["id"].isin(finished)]
        if done.empty:
            raise ValueError("No race with results yet.")
        return done["id"].iloc[-1]
    if spec not in set(races["id"]):
        raise ValueError(f"Unknown race id {spec!r} (expected e.g. 2026-17).")
    return spec


def auto_stage(t: Tables, race_id: str) -> Stage:
    """Post-qualifying once the qualifying classification is published, else pre."""
    return "post" if (t.qualifying["race_id"] == race_id).any() else "pre"


def _history(feats: pd.DataFrame, before_idx: int) -> pd.DataFrame:
    """Rows of completed races before ``before_idx`` with drivers who started."""
    done = feats["finish_order"].notna() & (feats["started"] == 1)
    return feats[done & (feats["race_idx"] < before_idx)]


def model_for(stage: Stage, t: Tables, race_id: str) -> RaceModel:
    """The saved model if it is trained through the last race before ``race_id``; else retrain.

    A retrained model is saved when it is newer than the saved one.
    """
    races = t.races.set_index("id")
    idx = races.loc[race_id, "race_idx"]
    finished = t.results.loc[t.results["session"] == "R", "race_id"].unique()
    before = races.loc[[r for r in finished if races.loc[r, "race_idx"] < idx]]
    if before.empty:
        raise ValueError("Need at least one completed race before the predicted race.")
    wanted = before.sort_values("race_idx").index[-1]

    saved = RaceModel.load(stage) if model_path(stage).exists() else None
    if saved is not None and saved.meta.get("trained_through") == wanted:
        return saved

    log.info("Training %s model on races through %s", stage, wanted)
    feats = build_features(stage, t)
    train = feats[
        (feats["race_idx"] < idx) & (feats["started"] == 1) & feats["finish_order"].notna()
    ]
    model = RaceModel(stage).fit(train)
    model.meta = {"trained_through": wanted}
    saved_idx = races.loc[saved.meta["trained_through"], "race_idx"] if saved else -1
    if races.loc[wanted, "race_idx"] > saved_idx:
        model.save(model_path(stage), trained_through=wanted)
    return model


@dataclass
class Snapshot:
    prediction: Prediction
    rows: pd.DataFrame


def predict(
    race_id: str, stage: Stage, now: datetime | None = None, engine: Engine | None = None
) -> int:
    """Predict ``race_id`` at ``stage`` and save an immutable snapshot. Returns its id."""
    now = now or utcnow()
    t = load_tables(engine)
    cut = cutoff(t, race_id, stage).to_pydatetime()
    feats = build_features(stage, truncate_to(t, race_id, stage), [race_id])
    model = model_for(stage, t, race_id)
    pred = model.predict_race(feats)

    with get_session(engine) as db:
        snap = Prediction(
            race_id=race_id,
            stage=stage,
            created_at=now,
            cutoff_utc=cut,
            made_before_cutoff=now < cut,
            model_trained_through=model.meta["trained_through"],
            temperature=model.temperature,
            incident_rate=model.incidents[0],
            incident_drop=model.incidents[1],
            model_version=__version__,
        )
        db.add(snap)
        db.flush()
        frame = pred.to_frame().assign(constructor_id=feats["constructor_id"].to_numpy())
        for i, r in enumerate(frame.itertuples()):
            db.add(
                PredictionRow(
                    prediction_id=snap.id,
                    driver_id=r.driver_id,
                    constructor_id=r.constructor_id,
                    pred_rank=int(r.pred_rank),
                    expected_pos=float(r.expected_pos),
                    p_win=float(r.p_win),
                    p_podium=float(r.p_podium),
                    p_points=float(r.p_points),
                    position_probs=json.dumps(np.round(pred.probs[i], 5).tolist()),
                    score=float(pred.scores[i]) if pred.scores is not None else None,
                    p_dnf=float(pred.p_dnf[i]) if pred.p_dnf is not None else None,
                )
            )
        db.commit()
        return snap.id


def load_snapshot(prediction_id: int, engine: Engine | None = None) -> Snapshot:
    engine = engine or get_engine()
    with get_session(engine) as db:
        snap = db.get(Prediction, prediction_id)
        db.expunge(snap)
    rows = pd.read_sql(
        select(PredictionRow).where(PredictionRow.prediction_id == prediction_id), engine
    ).sort_values("pred_rank")
    return Snapshot(snap, rows.reset_index(drop=True))


def latest_snapshot_id(race_id: str, stage: Stage, engine: Engine | None = None) -> int | None:
    with get_session(engine) as db:
        return db.scalar(
            select(Prediction.id)
            .where(Prediction.race_id == race_id, Prediction.stage == stage)
            .order_by(Prediction.id.desc())
        )


def _restrict(snapshot: Snapshot, driver_ids: list[str]) -> RacePrediction:
    """The snapshot's probability matrix for the drivers who actually started, rebalanced."""
    rows = snapshot.rows.set_index("driver_id").loc[driver_ids]
    n = len(driver_ids)
    probs = np.array([json.loads(p)[:n] for p in rows["position_probs"]]) + 1e-9
    return RacePrediction(snapshot.prediction.race_id, driver_ids, sinkhorn(probs))


def score_race(race_id: str, engine: Engine | None = None) -> list[int]:
    """Score every not-yet-scored snapshot of a finished race. Returns the scored ids."""
    engine = engine or get_engine()
    t = load_tables(engine)
    res = t.results[(t.results["race_id"] == race_id) & (t.results["session"] == "R")]
    if res.empty:
        raise ValueError(f"No race result for {race_id} yet.")
    with get_session(engine) as db:
        scored = set(db.scalars(select(PredictionScore.prediction_id)))
        snaps = [
            s
            for s in db.scalars(select(Prediction).where(Prediction.race_id == race_id))
            if s.id not in scored
        ]
        snap_ids = [(s.id, s.stage) for s in snaps]

    done = []
    for pid, stage in snap_ids:
        snapshot = load_snapshot(pid, engine)
        actual = res[res["position_text"].notna() & ~res["position_text"].isin(("W", "F", "E"))]
        common = [d for d in actual["driver_id"] if d in set(snapshot.rows["driver_id"])]
        missing = set(actual["driver_id"]) - set(common)
        if missing:
            log.warning("Snapshot %d did not include starters %s; scoring the rest", pid, missing)
        actual = actual.set_index("driver_id").loc[common].reset_index()
        truth = rank_within([actual["position_order"].to_numpy(dtype=float)])
        metrics = race_metrics(_restrict(snapshot, common), truth)
        base_name, base_metrics = _baseline_metrics(t, race_id, stage, common, truth)
        with get_session(engine) as db:
            db.add(
                PredictionScore(
                    prediction_id=pid,
                    scored_at=utcnow(),
                    n_drivers=len(common),
                    baseline_name=base_name,
                    baseline_metrics=json.dumps(base_metrics),
                    **metrics,
                )
            )
            db.commit()
        done.append(pid)
    return done


def _baseline_metrics(t: Tables, race_id: str, stage: Stage, drivers: list[str], truth):
    """Grid order (post) or championship order (pre) on the same race, for context."""
    baseline = grid_baseline() if stage == "post" else championship_baseline()
    feats = build_features(stage, t)
    idx = t.races.loc[t.races["id"] == race_id, "race_idx"].iloc[0]
    hist = feats[
        (feats["race_idx"] < idx) & (feats["started"] == 1) & feats["finish_order"].notna()
    ]
    baseline.fit(hist)
    race = feats[feats["race_id"] == race_id].set_index("driver_id").loc[drivers].reset_index()
    return baseline.name, race_metrics(baseline.predict_race(race), truth)


def track_record(engine: Engine | None = None) -> pd.DataFrame:
    engine = engine or get_engine()
    q = """
        select p.id, p.race_id, r.name as race, p.stage, p.created_at, p.made_before_cutoff,
               s.spearman, s.winner_hit, s.top3_hit, s.win_logloss, s.baseline_name,
               s.baseline_metrics
        from predictions p
        join races r on r.id = p.race_id
        left join prediction_scores s on s.prediction_id = p.id
        order by r.season, r.round, p.stage desc, p.id
    """
    df = pd.read_sql(q, engine)
    base = df["baseline_metrics"].dropna().map(json.loads)
    df.loc[base.index, "base_spearman"] = base.map(lambda m: m["spearman"])
    df.loc[base.index, "base_win_logloss"] = base.map(lambda m: m["win_logloss"])
    return df.drop(columns="baseline_metrics")
