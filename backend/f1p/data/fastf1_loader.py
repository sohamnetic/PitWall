"""FastF1 session loading: lap tables to parquet plus a per-session weather summary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import fastf1
import pandas as pd

from f1p import config

log = logging.getLogger(__name__)

SESSION_CODES = ("FP1", "FP2", "FP3", "SQ", "S", "Q", "R")

_NAME_TO_CODE = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Race": "R",
    "Sprint": "S",
    "Sprint Shootout": "SQ",
    "Sprint Qualifying": "SQ",
}

LAP_COLUMNS = [
    "Driver", "DriverNumber", "Team", "LapNumber", "LapTime", "Stint", "Compound", "TyreLife",
    "FreshTyre", "PitInTime", "PitOutTime", "Sector1Time", "Sector2Time", "Sector3Time",
    "SpeedST", "IsPersonalBest", "LapStartTime", "TrackStatus", "Position", "Deleted",
    "IsAccurate",
]  # fmt: skip

_initialised = False


def init_fastf1() -> None:
    global _initialised
    if not _initialised:
        config.FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(config.FASTF1_CACHE_DIR))
        fastf1.set_log_level("ERROR")
        _initialised = True


def session_code(name: str, event_format: str) -> str | None:
    """Map a FastF1 session name to our short code.

    In the 2021 sprint format, "Sprint Qualifying" was the name of the sprint race itself.
    """
    if name == "Sprint Qualifying" and event_format == "sprint":
        return "S"
    return _NAME_TO_CODE.get(name)


@dataclass
class ScheduledSession:
    season: int
    round: int
    code: str
    name: str
    start_utc: pd.Timestamp | None


def season_sessions(season: int) -> list[ScheduledSession]:
    init_fastf1()
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    out = []
    for _, ev in schedule.iterrows():
        if int(ev["RoundNumber"]) == 0:
            continue
        for i in range(1, 6):
            name = ev.get(f"Session{i}")
            if not isinstance(name, str) or not name:
                continue
            code = session_code(name, ev["EventFormat"])
            if code is None:
                continue
            start = ev.get(f"Session{i}DateUtc")
            out.append(
                ScheduledSession(
                    season=season,
                    round=int(ev["RoundNumber"]),
                    code=code,
                    name=name,
                    start_utc=None if pd.isna(start) else pd.Timestamp(start),
                )
            )
    return out


def laps_path(season: int, round_: int, code: str) -> Path:
    return config.LAPS_DIR / str(season) / f"{round_:02d}_{code}.parquet"


def tidy_laps(laps: pd.DataFrame, driver_ids: dict[str, str]) -> pd.DataFrame:
    """Keep the useful columns, convert timedeltas to float seconds, add ``DriverId``."""
    df = laps[[c for c in LAP_COLUMNS if c in laps.columns]].copy()
    for col in df.columns:
        if pd.api.types.is_timedelta64_dtype(df[col]):
            df[col] = df[col].dt.total_seconds()
    df = df.rename(
        columns={
            "LapTime": "LapTimeS",
            "PitInTime": "PitInTimeS",
            "PitOutTime": "PitOutTimeS",
            "Sector1Time": "Sector1S",
            "Sector2Time": "Sector2S",
            "Sector3Time": "Sector3S",
            "LapStartTime": "LapStartTimeS",
        }
    )
    for col in ("Deleted", "IsAccurate", "IsPersonalBest", "FreshTyre"):
        if col in df.columns:
            df[col] = df[col].astype("boolean").fillna(False).astype(bool)
    df["DriverId"] = df["Driver"].map(driver_ids)
    df["TrackStatus"] = df["TrackStatus"].astype("string")
    return df.reset_index(drop=True)


def weather_summary(weather: pd.DataFrame | None) -> dict:
    if weather is None or weather.empty:
        return {}
    return {
        "air_temp": float(weather["AirTemp"].mean()),
        "track_temp": float(weather["TrackTemp"].mean()),
        "humidity": float(weather["Humidity"].mean()),
        "wind_speed": float(weather["WindSpeed"].mean()),
        "rainfall_frac": float(weather["Rainfall"].astype(float).mean()),
    }


def load_session(s: ScheduledSession) -> tuple[pd.DataFrame, dict]:
    """Load a session's laps and weather. Returns an empty frame when no timing data exists."""
    init_fastf1()
    session = fastf1.get_session(s.season, s.round, s.name)
    session.load(laps=True, telemetry=False, weather=True, messages=False)
    try:
        laps = session.laps
    except fastf1.core.DataNotLoadedError:
        return pd.DataFrame(), {}
    if laps is None or laps.empty:
        return pd.DataFrame(), {}

    driver_ids = {}
    results = session.results
    if results is not None and "DriverId" in results:
        driver_ids = {
            a: d for a, d in zip(results["Abbreviation"], results["DriverId"]) if a and d
        }
    try:
        weather = session.weather_data
    except fastf1.core.DataNotLoadedError:
        weather = None
    return tidy_laps(laps, driver_ids), weather_summary(weather)
