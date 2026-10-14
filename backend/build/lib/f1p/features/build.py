"""Assemble the point-in-time feature matrix: one row per (race, driver) for a stage."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from f1p.features.circuit import CIRCUIT_TYPES, circuit_features, driver_circuit_features
from f1p.features.form import (
    championship_features,
    driver_features,
    race_panel,
    team_features,
)
from f1p.features.pace import weekend_pace, weekend_weather
from f1p.features.tables import Stage, Tables, cutoff, load_tables

log = logging.getLogger(__name__)

ID_COLS = ["race_id", "season", "round", "race_idx", "driver_id", "constructor_id"]
TARGET_COLS = ["finish_order", "finish_pos", "classified", "dnf", "started", "points"]

PRE_FEATURES = [
    # driver history
    "drv_form", "drv_pace_form", "drv_quali_form", "drv_last_pos_pct", "tm_quali_delta",
    "tm_race_delta", "drv_starts", "seat_starts", "drv_dnf_rate", "season_pts_before",
    "champ_rank_pct", "drv_circuit_pct", "drv_circuit_n",
    # team history
    "team_form", "team_pace_form", "team_quali_form", "team_era_form", "team_era_quali_form",
    "team_era_races", "team_dnf_rate",
    # circuit / calendar
    "circuit_type", "circuit_grid_rho", "races_into_era", "season_round", "sprint_weekend",
    "field_size",
    # this weekend so far
    "fp_best_gap_pct", "fp_long_run_gap_pct", "fp_clean_laps", "sq_gap_pct", "fp_best_rank_pct",
    "fp_long_run_rank_pct", "sq_rank_pct", "sprint_pos_pct", "wx_rain_frac", "wx_track_temp",
]  # fmt: skip
POST_FEATURES = PRE_FEATURES + [
    "quali_pos_pct", "quali_gap_pct", "grid_pct", "pitlane_start", "grid_x_rho",
]  # fmt: skip
CATEGORICAL_FEATURES = ["circuit_type"]


def feature_columns(stage: Stage) -> list[str]:
    return PRE_FEATURES if stage == "pre" else POST_FEATURES


def entries_for(t: Tables, race_id: str) -> pd.DataFrame:
    """Who is racing: from the race sheet, else qualifying, sprint, practice laps, last lineup."""
    cols = ["driver_id", "constructor_id"]
    res = t.results
    for frame in (
        res[(res["race_id"] == race_id) & (res["session"] == "R")],
        t.qualifying[t.qualifying["race_id"] == race_id],
        res[(res["race_id"] == race_id) & (res["session"] == "S")],
    ):
        if not frame.empty:
            return frame[cols].assign(race_id=race_id)

    idx = t.races.loc[t.races["id"] == race_id, "race_idx"].iloc[0]
    past = res[res["session"] == "R"].merge(
        t.races[["id", "race_idx"]], left_on="race_id", right_on="id"
    )
    past = past[past["race_idx"] < idx].sort_values("race_idx")
    latest_team = past.groupby("driver_id")["constructor_id"].last()

    sess = t.sessions[
        (t.sessions["race_id"] == race_id)
        & (t.sessions["status"] == "ok")
        & t.sessions["session"].isin(["FP1", "FP2", "FP3", "SQ"])
    ].sort_values("start_utc")
    if not sess.empty:
        # The latest session best reflects the race line-up: FP1 often has reserve drivers.
        laps = t.laps(sess["laps_path"].iloc[-1])
        drivers = set(laps["DriverId"].dropna())
        # Codes get reused across eras (VER: Vergne, then Verstappen): recent drivers only.
        recent = past.loc[past["race_idx"] >= past["race_idx"].max() - 10, "driver_id"]
        codes = (
            t.drivers[t.drivers["id"].isin(set(recent))]
            .dropna()
            .drop_duplicates("code", keep=False)
            .set_index("code")["id"]
        )
        drivers |= set(laps.loc[laps["DriverId"].isna(), "Driver"].map(codes).dropna())
        out = pd.DataFrame({"driver_id": sorted(drivers)})
        out["constructor_id"] = out["driver_id"].map(latest_team)
        return out.dropna().assign(race_id=race_id)

    last_race = past["race_idx"].max()
    return past[past["race_idx"] == last_race][cols].assign(race_id=race_id)


def _weekend_features(t: Tables, race_id: str, stage: Stage, drivers: pd.Index) -> pd.DataFrame:
    cut = cutoff(t, race_id, stage)
    out = pd.DataFrame(index=drivers)
    out = out.join(weekend_pace(t, race_id, cut))
    for k, v in weekend_weather(t, race_id, cut).items():
        out[k] = v

    race = t.races.loc[t.races["id"] == race_id].iloc[0]
    sprint = t.results[(t.results["race_id"] == race_id) & (t.results["session"] == "S")]
    out["sprint_weekend"] = float(race["weekend_format"] == "sprint" or not sprint.empty)
    if not sprint.empty and race["sprint_start"] < cut:
        n = sprint["position_order"].max()
        out["sprint_pos_pct"] = sprint.set_index("driver_id")["position_order"].sub(1).div(n - 1)
    else:
        out["sprint_pos_pct"] = np.nan

    if stage == "post":
        out = out.join(_quali_features(t, race_id, drivers))
    return out


def _quali_features(t: Tables, race_id: str, drivers: pd.Index) -> pd.DataFrame:
    n = len(drivers)
    q = t.qualifying[t.qualifying["race_id"] == race_id].set_index("driver_id")
    out = pd.DataFrame(index=drivers)
    if not q.empty:
        best = q[["q1_s", "q2_s", "q3_s"]].min(axis=1)
        out["quali_pos_pct"] = (q["position"] - 1) / (q["position"].max() - 1)
        out["quali_gap_pct"] = (best / best.min() - 1) * 100
    else:
        out["quali_pos_pct"] = out["quali_gap_pct"] = np.nan

    res = t.results[(t.results["race_id"] == race_id) & (t.results["session"] == "R")]
    grid = res.set_index("driver_id")["grid"].reindex(drivers)
    if grid.isna().all() and not q.empty:
        grid = q["position"].reindex(drivers)  # race sheet not out yet: grid ~ quali order
    out["pitlane_start"] = (grid == 0).astype(float).where(grid.notna())
    grid_pos = grid.where(grid != 0, n)
    out["grid_pct"] = (grid_pos - 1) / max(n - 1, 1)
    return out


def build_features(
    stage: Stage, t: Tables | None = None, race_ids: list[str] | None = None
) -> pd.DataFrame:
    """Feature matrix for ``race_ids`` (default: every race with a result) at ``stage``."""
    t = t or load_tables()
    have_results = set(t.results.loc[t.results["session"] == "R", "race_id"])
    if race_ids is None:
        race_ids = [r for r in t.races["id"] if r in have_results]

    entries = pd.concat([entries_for(t, rid) for rid in race_ids], ignore_index=True)
    panel = race_panel(t, entries)
    hist = pd.concat(
        [
            panel[["race_id", "driver_id", "constructor_id", "race_idx", "season"]],
            driver_features(panel),
            team_features(panel),
            championship_features(t, panel),
            driver_circuit_features(panel, t.races),
        ],
        axis=1,
    )
    df = entries[["race_id", "driver_id"]].merge(hist, on=["race_id", "driver_id"], how="left")

    races = t.races.set_index("id")
    df["round"] = df["race_id"].map(races["round"])
    era_start = t.races.groupby("regs_era")["race_idx"].transform("min")
    df["races_into_era"] = df["race_id"].map(
        pd.Series((t.races["race_idx"] - era_start).values, index=t.races["id"])
    )
    df["season_round"] = df["round"]
    df["field_size"] = df.groupby("race_id")["driver_id"].transform("count")
    df = df.join(circuit_features(t), on="race_id")

    weekend = []
    for rid, g in df.groupby("race_id", sort=False):
        w = _weekend_features(t, rid, stage, pd.Index(g["driver_id"], name="driver_id"))
        weekend.append(w.reset_index().assign(race_id=rid))
    df = df.merge(pd.concat(weekend, ignore_index=True), on=["race_id", "driver_id"], how="left")

    if stage == "post":
        df["grid_x_rho"] = df["grid_pct"] * df["circuit_grid_rho"]

    df = df.join(_targets(t), on=["race_id", "driver_id"])
    df["circuit_type"] = pd.Categorical(df["circuit_type"], categories=CIRCUIT_TYPES)
    # All-NULL database columns come back as object dtype; models need numbers.
    for c in feature_columns(stage):
        if c not in CATEGORICAL_FEATURES and c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)

    cols = ID_COLS + feature_columns(stage) + TARGET_COLS
    for c in cols:
        if c not in df:
            df[c] = np.nan
    return df[cols].sort_values(["race_idx", "driver_id"]).reset_index(drop=True)


def _targets(t: Tables) -> pd.DataFrame:
    r = t.results[t.results["session"] == "R"].set_index(["race_id", "driver_id"])
    started = r["position_text"].notna() & ~r["position_text"].isin(("W", "F", "E"))
    return pd.DataFrame(
        {
            "finish_order": r["position_order"],
            "finish_pos": r["position"],
            "classified": r["classified"].astype(float).where(r["position_text"].notna()),
            "dnf": r["position_text"].isin(("R", "N")).astype(float).where(started),
            "started": started.astype(float).where(r["position_text"].notna()),
            "points": r["points"],
        }
    )
