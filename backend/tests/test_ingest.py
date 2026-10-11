from datetime import date, datetime

import pandas as pd
import pytest
from sqlalchemy import func, select

from f1p.data import jolpica as jp
from f1p.data.db import get_engine, get_session, upsert
from f1p.data.fastf1_loader import session_code, tidy_laps, weather_summary
from f1p.data.ingest import parse_seasons
from f1p.data.models import Constructor, Driver, Race, Result

DRIVER = {
    "driverId": "russell", "permanentNumber": "63", "code": "RUS", "givenName": "George",
    "familyName": "Russell", "dateOfBirth": "1998-02-15", "nationality": "British",
}  # fmt: skip
CONSTRUCTOR = {"constructorId": "mercedes", "name": "Mercedes", "nationality": "German"}

RACE = {
    "season": "2026",
    "round": "17",
    "raceName": "Singapore Grand Prix",
    "Circuit": {
        "circuitId": "marina_bay",
        "circuitName": "Marina Bay Street Circuit",
        "Location": {"locality": "Marina Bay", "country": "Singapore"},
    },
    "date": "2026-10-11",
    "time": "12:00:00Z",
    "Qualifying": {"date": "2026-10-10", "time": "13:00:00Z"},
    "Sprint": {"date": "2026-10-10", "time": "09:00:00Z"},
    "Results": [
        {
            "number": "63",
            "position": "1",
            "positionText": "1",
            "points": "25",
            "Driver": DRIVER,
            "Constructor": CONSTRUCTOR,
            "grid": "1",
            "laps": "62",
            "status": "Finished",
            "Time": {"millis": "6000000"},
        },
        {
            "number": "12",
            "position": "22",
            "positionText": "R",
            "points": "0",
            "Driver": {**DRIVER, "driverId": "antonelli", "code": "ANT"},
            "Constructor": CONSTRUCTOR,
            "grid": "0",
            "laps": "3",
            "status": "Retired",
        },
    ],  # fmt: skip
}


def test_parse_seasons():
    assert parse_seasons("2024") == [2024]
    assert parse_seasons("2018-2020") == [2018, 2019, 2020]
    assert parse_seasons("2019, 2021-2022") == [2019, 2021, 2022]


@pytest.mark.parametrize(
    ("text", "seconds"), [("1:36.477", 96.477), ("58.1", 58.1), ("", None), (None, None)]
)
def test_lap_time_to_seconds(text, seconds):
    assert jp.lap_time_to_seconds(text) == seconds


def test_parse_race():
    race = jp.parse_race(RACE)
    assert race["id"] == "2026-17"
    assert race["race_date"] == date(2026, 10, 11)
    assert race["race_start_utc"] == datetime(2026, 10, 11, 12, 0)
    assert race["quali_start_utc"] == datetime(2026, 10, 10, 13, 0)
    assert race["sprint_start_utc"] == datetime(2026, 10, 10, 9, 0)
    assert race["weekend_format"] == "sprint"


def test_parse_result_rows_marks_dnf_and_pitlane_start():
    winner, dnf = jp.parse_result_rows(RACE, "R")
    assert winner["position"] == 1 and winner["classified"] and winner["time_ms"] == 6000000
    assert dnf["position"] is None and not dnf["classified"]
    assert dnf["position_text"] == "R" and dnf["position_order"] == 22 and dnf["grid"] == 0


def test_upsert_is_idempotent(tmp_path):
    engine = get_engine(tmp_path / "test.sqlite")
    rows = jp.parse_result_rows(RACE, "R")
    with get_session(engine) as db:
        upsert(db, Race, [jp.parse_race(RACE)], ["id"])
        upsert(db, Constructor, [jp.parse_constructor(CONSTRUCTOR)], ["id"])
        upsert(
            db, Driver,
            [jp.parse_driver(r["Driver"]) for r in RACE["Results"]], ["id"],
        )  # fmt: skip
        upsert(db, Result, rows, ["race_id", "session", "driver_id"])
        rows[0]["points"] = 26.0  # e.g. a corrected classification
        upsert(db, Result, rows, ["race_id", "session", "driver_id"])
        db.commit()
        assert db.scalar(select(func.count()).select_from(Result)) == 2
        assert db.scalar(select(Result.points).where(Result.driver_id == "russell")) == 26.0


def test_session_code():
    assert session_code("Practice 2", "conventional") == "FP2"
    assert session_code("Sprint Qualifying", "sprint_qualifying") == "SQ"
    assert session_code("Sprint Qualifying", "sprint") == "S"  # 2021 naming
    assert session_code("Sprint Shootout", "sprint_shootout") == "SQ"
    assert session_code("Pre-Season Test", "testing") is None


def test_tidy_laps_converts_timedeltas_and_maps_driver_ids():
    laps = pd.DataFrame(
        {
            "Driver": ["NOR", "VER"],
            "LapTime": pd.to_timedelta([100.5, None], unit="s"),
            "LapNumber": [2.0, 1.0],
            "Deleted": [None, True],
            "TrackStatus": ["1", "4"],
        }
    )
    out = tidy_laps(laps, {"NOR": "norris"})
    assert out["LapTimeS"].iloc[0] == pytest.approx(100.5)
    assert pd.isna(out["LapTimeS"].iloc[1])
    assert out["Deleted"].tolist() == [False, True]
    assert out["DriverId"].tolist()[0] == "norris" and pd.isna(out["DriverId"].iloc[1])


def test_weather_summary():
    w = pd.DataFrame(
        {"AirTemp": [30, 32], "TrackTemp": [40, 44], "Humidity": [70, 80],
         "WindSpeed": [1, 3], "Rainfall": [False, True]}
    )  # fmt: skip
    s = weather_summary(w)
    assert s["air_temp"] == 31 and s["rainfall_frac"] == 0.5
    assert weather_summary(None) == {}
