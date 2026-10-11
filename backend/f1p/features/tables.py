"""Load the database into DataFrames, plus point-in-time cutoffs and truncation.

Every feature is computed "as of" a cutoff:

- ``pre`` stage: the start of qualifying. Practice, sprint qualifying and (in the 2024+ format)
  the sprint itself are known; qualifying and the grid are not.
- ``post`` stage: the start of the race. Qualifying and the final grid are known.

History features (form, reliability, circuit record) only ever use earlier races.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd
from sqlalchemy import Engine

from f1p import config
from f1p.data.db import get_engine

Stage = Literal["pre", "post"]

PRACTICE_SESSIONS = ("FP1", "FP2", "FP3")
DNF_CODES = ("R", "N")  # retired, not classified (did not complete 90% distance)
DID_NOT_START_CODES = ("W", "F", "E")  # withdrawn, failed to qualify, excluded


@dataclass(frozen=True)
class Tables:
    races: pd.DataFrame
    results: pd.DataFrame  # sessions "R" and "S"
    qualifying: pd.DataFrame
    sessions: pd.DataFrame  # FastF1 session records (laps_path, weather, start_utc)
    drivers: pd.DataFrame  # id, code

    def laps(self, laps_path: str) -> pd.DataFrame:
        return pd.read_parquet(config.DATA_DIR / laps_path)


def load_tables(engine: Engine | None = None) -> Tables:
    engine = engine or get_engine()
    races = pd.read_sql(
        "select * from races",
        engine,
        parse_dates=["race_date", "race_start_utc", "quali_start_utc", "sprint_start_utc"],
    )
    results = pd.read_sql("select * from results", engine)
    results["classified"] = results["classified"].astype(bool)
    qualifying = pd.read_sql("select * from qualifying", engine)
    sessions = pd.read_sql("select * from sessions", engine, parse_dates=["start_utc"])
    drivers = pd.read_sql("select id, code from drivers", engine)
    return prepare_tables(races, results, qualifying, sessions, drivers)


def prepare_tables(races, results, qualifying, sessions, drivers) -> Tables:
    """Add the derived columns every feature module relies on."""
    races = races.sort_values(["season", "round"]).reset_index(drop=True).copy()
    races["race_idx"] = range(len(races))
    races["regs_era"] = races["season"].map(config.regulation_era)

    q_session = sessions[sessions["session"] == "Q"].set_index("race_id")["start_utc"]
    s_session = sessions[sessions["session"] == "S"].set_index("race_id")["start_utc"]
    race_day = pd.to_datetime(races["race_date"])
    races["pre_cutoff"] = (
        races["quali_start_utc"]
        .fillna(races["id"].map(q_session))
        .fillna(race_day - pd.Timedelta(days=1))
    )
    races["post_cutoff"] = races["race_start_utc"].fillna(race_day)
    # Sprint start unknown (e.g. 2021 calendar): in that era the sprint ran the day after
    # qualifying, so place it just after qualifying.
    races["sprint_start"] = (
        races["sprint_start_utc"]
        .fillna(races["id"].map(s_session))
        .fillna(races["pre_cutoff"] + pd.Timedelta(hours=1))
    )
    return Tables(
        races=races, results=results, qualifying=qualifying, sessions=sessions, drivers=drivers
    )


def cutoff(t: Tables, race_id: str, stage: Stage) -> pd.Timestamp:
    row = t.races.loc[t.races["id"] == race_id].iloc[0]
    return row[f"{stage}_cutoff"]


def truncate_to(t: Tables, race_id: str, stage: Stage) -> Tables:
    """What the world looked like at ``stage`` cutoff of ``race_id``.

    Later races vanish entirely. The race itself keeps only its entry list (and the grid,
    post-qualifying); sessions and the sprint are kept only if they started before the cutoff.
    Used by the leakage tests and for honest as-of predictions.
    """
    races = t.races
    idx = races.loc[races["id"] == race_id, "race_idx"].iloc[0]
    later = set(races.loc[races["race_idx"] > idx, "id"])
    cut = cutoff(t, race_id, stage)
    sprint_known = races.loc[races["id"] == race_id, "sprint_start"].iloc[0] < cut

    res = t.results[~t.results["race_id"].isin(later)].copy()
    this_race = (res["race_id"] == race_id) & (res["session"] == "R")
    blank = ["position", "position_text", "position_order", "points", "laps", "status", "time_ms"]
    res.loc[this_race, blank] = None
    res.loc[this_race, "classified"] = False
    if stage == "pre":
        res.loc[this_race, "grid"] = None
    if not sprint_known:
        res = res[~((res["race_id"] == race_id) & (res["session"] == "S"))]

    quali = t.qualifying[~t.qualifying["race_id"].isin(later)]
    if stage == "pre":
        quali = quali[quali["race_id"] != race_id]

    sess = t.sessions[~t.sessions["race_id"].isin(later)]
    sess = sess[(sess["race_id"] != race_id) | (sess["start_utc"] < cut)]
    return replace(t, results=res, qualifying=quali, sessions=sess)
