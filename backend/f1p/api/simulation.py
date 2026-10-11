"""On-demand simulations behind 'Ask the model' and the what-if grid editor."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from f1p.config import N_SIMULATIONS
from f1p.features.build import build_features
from f1p.features.tables import load_tables, truncate_to
from f1p.models import questions as qs
from f1p.models import scenario as sc
from f1p.models.base import RacePrediction
from f1p.models.race_model import RaceModel, model_path
from f1p.models.simulate import position_probs, simulate_races

CACHE_TTL_S = 300


class SimulationUnavailable(Exception):
    """The request can't be served for this race (no prediction, race already run, ...)."""


@dataclass
class Inputs:
    driver_ids: list[str]
    teams: dict[str, str]
    scores: np.ndarray
    p_dnf: np.ndarray
    temperature: float
    source: str  # "snapshot" | "scenario"
    snapshot_id: int | None
    stage: str
    grid: list[str] | None = None


_lock = threading.Lock()
_rows_cache: dict[str, tuple[float, pd.DataFrame, pd.Series]] = {}
_model_cache: dict[str, tuple[float, RaceModel]] = {}


def _post_model() -> RaceModel:
    path = model_path("post")
    if not path.exists():
        raise SimulationUnavailable("no trained model yet: run `f1p train`")
    mtime = path.stat().st_mtime
    with _lock:
        cached = _model_cache.get("post")
        if cached and cached[0] == mtime:
            return cached[1]
        model = RaceModel.load("post")
        _model_cache["post"] = (mtime, model)
        return model


def _base_rows(engine: Engine, race_id: str) -> tuple[pd.DataFrame, pd.Series]:
    """Post-qualifying feature rows as of now, plus typical qualifying gaps (cached briefly)."""
    with _lock:
        cached = _rows_cache.get(race_id)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
            return cached[1], cached[2]
    t = load_tables(engine)
    has_quali = (t.qualifying["race_id"] == race_id).any()
    asof = truncate_to(t, race_id, "post" if has_quali else "pre")
    rows = build_features("post", asof, [race_id])
    gaps = sc.typical_quali_gaps(t)
    with _lock:
        _rows_cache[race_id] = (time.monotonic(), rows, gaps)
    return rows, gaps


def _race_status(engine: Engine, race_id: str) -> dict:
    df = pd.read_sql(
        text(
            """select ra.id,
                 (select count(*) from results r where r.race_id = ra.id and r.session = 'R'
                    and coalesce(r.source, 'jolpica') = 'jolpica') as n_official
               from races ra where ra.id = :r"""
        ),
        engine,
        params={"r": race_id},
    )
    if df.empty:
        raise KeyError(race_id)
    return {"completed": bool(df["n_official"].iloc[0])}


def _snapshot_inputs(engine: Engine, race_id: str, stage: str | None) -> Inputs:
    stages = [stage] if stage else ["post", "pre"]
    for st in stages:
        snap = pd.read_sql(
            text(
                "select id, temperature from predictions where race_id = :r and stage = :s "
                "order by id desc limit 1"
            ),
            engine,
            params={"r": race_id, "s": st},
        )
        if snap.empty:
            continue
        pid = int(snap["id"].iloc[0])
        rows = pd.read_sql(
            # Original insertion order: the simulation draws per driver column, so the same
            # order with the same seed reproduces the saved probabilities exactly.
            text("select * from prediction_rows where prediction_id = :i order by id"),
            engine,
            params={"i": pid},
        )
        if rows["score"].isna().any():
            raise SimulationUnavailable(
                "this prediction was saved before questions were supported; "
                "make a fresh one with `f1p predict`"
            )
        return Inputs(
            driver_ids=list(rows["driver_id"]),
            teams=dict(zip(rows["driver_id"], rows["constructor_id"], strict=True)),
            scores=rows["score"].to_numpy(float),
            p_dnf=rows["p_dnf"].to_numpy(float),
            temperature=float(snap["temperature"].iloc[0]),
            source="snapshot",
            snapshot_id=pid,
            stage=st,
        )
    raise SimulationUnavailable(f"no prediction for {race_id} yet")


def _scenario_inputs(engine: Engine, race_id: str, scenario: sc.Scenario) -> Inputs:
    if _race_status(engine, race_id)["completed"]:
        raise SimulationUnavailable(
            "what-if scenarios are only for upcoming races (the current model has seen this "
            "race's result)"
        )
    base, gaps = _base_rows(engine, race_id)
    rows = sc.apply(base, scenario, gaps)
    model = _post_model()
    scores, p_dnf, temperature = sc.simulation_inputs(model, rows, scenario)
    grid = list(rows.sort_values("grid_pct")["driver_id"])
    return Inputs(
        driver_ids=list(rows["driver_id"]),
        teams=dict(zip(rows["driver_id"], rows["constructor_id"], strict=True)),
        scores=scores,
        p_dnf=p_dnf,
        temperature=temperature,
        source="scenario",
        snapshot_id=None,
        stage="post",
        grid=grid,
    )


def race_field(engine: Engine, race_id: str) -> dict:
    """Who is racing, their teams and the current (or predicted) starting order."""
    status = _race_status(engine, race_id)
    base, _ = _base_rows(engine, race_id)
    current = base["grid_pct"].fillna(base["quali_pos_pct"])
    has_grid = current.notna().any()
    if has_grid:
        order = list(base.assign(_g=current).sort_values("_g", na_position="last")["driver_id"])
    else:
        try:
            order = _snapshot_inputs(engine, race_id, None).driver_ids  # predicted order
        except SimulationUnavailable:
            order = list(base.sort_values("team_form")["driver_id"])
    return {
        "race_id": race_id,
        "completed": status["completed"],
        "grid_source": "qualifying" if has_grid else "predicted",
        "order": order,
        "teams": dict(zip(base["driver_id"], base["constructor_id"], strict=True)),
    }


def run(
    engine: Engine,
    race_id: str,
    scenario: sc.Scenario | None,
    questions: list[qs.Question],
    stage: str | None = None,
    n_sims: int = N_SIMULATIONS,
) -> dict:
    status = _race_status(engine, race_id)
    if scenario is None or scenario.is_noop():
        inp = _snapshot_inputs(engine, race_id, stage)
    else:
        inp = _scenario_inputs(engine, race_id, scenario)

    finish, retired = simulate_races(inp.scores, inp.p_dnf, inp.temperature, n_sims, seed=0)
    pred = RacePrediction(race_id, inp.driver_ids, position_probs(finish))
    field_ = qs.Field(inp.driver_ids, inp.teams, finish, retired)
    actual = _actual_field(engine, race_id, inp) if status["completed"] else None

    answers = []
    for q in questions:
        try:
            p = qs.answer(q, field_)
            happened = bool(qs.outcomes(q, actual)[0]) if actual else None
            answers.append({"question": q, "probability": p, "happened": happened, "error": None})
        except qs.QuestionError as e:
            answers.append({"question": q, "probability": None, "happened": None, "error": str(e)})

    return {
        "race_id": race_id,
        "source": inp.source,
        "snapshot_id": inp.snapshot_id,
        "stage": inp.stage,
        "n_sims": n_sims,
        "temperature": inp.temperature,
        "grid": inp.grid,
        "frame": pred.to_frame().assign(
            constructor_id=[inp.teams.get(d) for d in inp.driver_ids],
            position_probs=[json.dumps(np.round(r, 5).tolist()) for r in pred.probs],
        ),
        "answers": answers,
    }


def _actual_field(engine: Engine, race_id: str, inp: Inputs) -> qs.Field:
    res = pd.read_sql(
        text("select driver_id, position_order, position_text from results "
             "where race_id = :r and session = 'R'"),
        engine,
        params={"r": race_id},
    )  # fmt: skip
    order = dict(zip(res["driver_id"], res["position_order"], strict=True))
    dnfs = set(res.loc[res["position_text"].isin(["R", "N"]), "driver_id"])
    return qs.actual_field(inp.driver_ids, inp.teams, order, dnfs)
