"""Same-weekend pace from FastF1 laps, expressed relative to the field.

Absolute lap times mean nothing across circuits or regulation eras, so everything is a % gap
to the fastest driver in the same session.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1p.features.tables import PRACTICE_SESSIONS, Tables

LONG_RUN_MIN_LAPS = 5
LONG_RUN_MAX_SLOWDOWN = 1.07  # laps slower than 107% of the driver's best are not race pace


def clean_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Green-flag timed laps that are not in/out laps or deleted, with a known driver."""
    ok = (
        laps["LapTimeS"].notna()
        & laps["DriverId"].notna()
        & ~laps["Deleted"]
        & laps["PitInTimeS"].isna()
        & laps["PitOutTimeS"].isna()
        & (laps["TrackStatus"] == "1")
    )
    return laps[ok]


def session_pace(laps: pd.DataFrame) -> pd.DataFrame:
    """Per driver: best-lap gap %, long-run gap % and clean lap count for one session."""
    clean = clean_laps(laps)
    if clean.empty:
        return pd.DataFrame(columns=["best_gap_pct", "long_run_gap_pct", "clean_laps"])

    best = clean.groupby("DriverId")["LapTimeS"].min()
    out = pd.DataFrame({"best_gap_pct": (best / best.min() - 1) * 100})
    out["clean_laps"] = clean.groupby("DriverId").size()

    near = clean[clean["LapTimeS"] <= clean["DriverId"].map(best) * LONG_RUN_MAX_SLOWDOWN]
    stints = near.groupby(["DriverId", "Stint"])["LapTimeS"].agg(["median", "size"])
    stints = stints[stints["size"] >= LONG_RUN_MIN_LAPS]
    if not stints.empty:
        # Fastest representative race-sim stint per driver.
        long_run = stints.groupby("DriverId")["median"].min()
        out["long_run_gap_pct"] = (long_run / long_run.min() - 1) * 100
    else:
        out["long_run_gap_pct"] = np.nan
    return out


def weekend_pace(t: Tables, race_id: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Aggregate pace over the sessions of ``race_id`` that started before ``cutoff``."""
    sess = t.sessions[
        (t.sessions["race_id"] == race_id)
        & (t.sessions["start_utc"] < cutoff)
        & (t.sessions["status"] == "ok")
    ]
    sess = sess[sess["session"].isin((*PRACTICE_SESSIONS, "SQ"))]
    laps = {row["session"]: t.laps(row["laps_path"]) for _, row in sess.iterrows()}
    codes = _driver_codes(t, race_id, laps.values())
    frames = []
    for code, session_laps in laps.items():
        session_laps = session_laps.assign(
            DriverId=session_laps["DriverId"].fillna(session_laps["Driver"].map(codes))
        )
        pace = session_pace(session_laps)
        pace["session"] = code
        frames.append(pace.reset_index(names="driver_id"))

    if not frames:
        return pd.DataFrame(columns=["driver_id"]).set_index("driver_id")
    allp = pd.concat([f for f in frames if not f.empty])
    fp = allp[allp["session"].isin(PRACTICE_SESSIONS)]

    out = pd.DataFrame(index=pd.Index(allp["driver_id"].unique(), name="driver_id"))
    out["fp_best_gap_pct"] = fp.groupby("driver_id")["best_gap_pct"].min()
    out["fp_long_run_gap_pct"] = fp.groupby("driver_id")["long_run_gap_pct"].min()
    out["fp_clean_laps"] = fp.groupby("driver_id")["clean_laps"].sum()
    out["sq_gap_pct"] = allp[allp["session"] == "SQ"].groupby("driver_id")["best_gap_pct"].min()
    for col in ("fp_best_gap_pct", "fp_long_run_gap_pct", "sq_gap_pct"):
        out[col.replace("_gap_pct", "_rank_pct")] = out[col].rank(pct=True)
    out["fp_clean_laps"] = out["fp_clean_laps"].astype(float).fillna(0.0)
    return out


def _driver_codes(t: Tables, race_id: str, laps_frames) -> dict[str, str]:
    """Abbreviation -> driver id. FastF1 leaves DriverId empty in some sessions (e.g. SQ)."""
    race = t.races.loc[t.races["id"] == race_id].iloc[0]
    season_races = t.races.loc[
        (t.races["season"] == race["season"]) & (t.races["race_idx"] <= race["race_idx"]), "id"
    ]
    season_drivers = set(t.results.loc[t.results["race_id"].isin(season_races), "driver_id"])
    codes = (
        t.drivers[t.drivers["id"].isin(season_drivers)].dropna().set_index("code")["id"].to_dict()
    )
    for laps in laps_frames:  # the weekend's own mapping wins
        known = laps.dropna(subset=["DriverId"])
        codes.update(dict(zip(known["Driver"], known["DriverId"], strict=True)))
    return codes


def weekend_weather(t: Tables, race_id: str, cutoff: pd.Timestamp) -> dict:
    sess = t.sessions[
        (t.sessions["race_id"] == race_id)
        & (t.sessions["start_utc"] < cutoff)
        & (t.sessions["status"] == "ok")
    ].sort_values("start_utc")
    if sess.empty:
        return {"wx_rain_frac": np.nan, "wx_track_temp": np.nan}
    return {
        "wx_rain_frac": float(sess["rainfall_frac"].max()),
        "wx_track_temp": float(sess["track_temp"].iloc[-1]),
    }
