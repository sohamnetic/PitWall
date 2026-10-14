"""Provisional qualifying and sprint classifications derived from FastF1 lap timing.

Jolpica (and FastF1's own results, which come from Jolpica) can lag a weekend by a day or
more. To predict a race straight after qualifying we rebuild the classification from laps:

- qualifying: Q3 runners by best Q3 lap, then Q2 eliminations by best Q2 lap, then Q1;
- sprint: by laps completed, then position at the end of the last lap.

Rows are stored with ``source = "fastf1"`` and replaced by the official Jolpica rows (which
include penalties) as soon as those are published.
"""

from __future__ import annotations

import logging

import fastf1
import pandas as pd
from sqlalchemy import select

from f1p.data import jolpica as jp
from f1p.data.db import get_session, upsert
from f1p.data.fastf1_loader import init_fastf1
from f1p.data.models import Driver, QualifyingResult, Race, Result, SessionRecord

log = logging.getLogger(__name__)

SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1]


def _best_laps(laps) -> pd.Series:
    deleted = laps["Deleted"].astype("boolean").fillna(False).astype(bool)
    ok = laps[laps["LapTime"].notna() & ~deleted]
    return ok.groupby("Driver")["LapTime"].min().dt.total_seconds()


def qualifying_order(q1, q2, q3) -> pd.DataFrame:
    """Classification from the three knockout segments' laps (FastF1 ``Laps`` objects)."""
    best = {name: _best_laps(q) if q is not None else pd.Series(dtype=float)
            for name, q in (("q1", q1), ("q2", q2), ("q3", q3))}  # fmt: skip
    drivers = set(q1["Driver"]) if q1 is not None else set()
    in_q2 = set(q2["Driver"]) if q2 is not None else set()
    in_q3 = set(q3["Driver"]) if q3 is not None else set()
    df = pd.DataFrame({"Driver": sorted(drivers | in_q2 | in_q3)})
    for name, s in best.items():
        df[f"{name}_s"] = df["Driver"].map(s)
    df["stage"] = df["Driver"].map(lambda d: 3 if d in in_q3 else 2 if d in in_q2 else 1)
    df["key"] = df.apply(lambda r: r[f"q{r['stage']}_s"], axis=1)
    df = df.sort_values(["stage", "key"], ascending=[False, True], na_position="last")
    df["position"] = range(1, len(df) + 1)
    return df.reset_index(drop=True)


def sprint_order(laps: pd.DataFrame) -> pd.DataFrame:
    """Classification from sprint laps: laps completed, then last recorded position."""
    last = laps.sort_values("LapNumber").groupby("Driver").tail(1)
    df = last[["Driver", "LapNumber", "Position"]].rename(columns={"LapNumber": "laps"})
    df = df.sort_values(["laps", "Position"], ascending=[False, True], na_position="last")
    df["position_order"] = range(1, len(df) + 1)
    df["classified"] = df["laps"] >= 0.9 * df["laps"].max()
    return df.reset_index(drop=True)


def _driver_lookup(season: int, round_: int) -> tuple[dict, dict]:
    """Abbreviation -> driver id and driver id -> latest constructor, from earlier races."""
    with get_session() as db:
        rows = db.execute(
            select(Result.driver_id, Result.constructor_id, Driver.code, Race.season, Race.round)
            .join(Driver, Driver.id == Result.driver_id)
            .join(Race, Race.id == Result.race_id)
            .where(Race.season == season, Race.round < round_, Result.session == "R")
            .order_by(Race.round)
        ).all()
    codes = {code: drv for drv, _, code, _, _ in rows}
    teams = {drv: cons for drv, cons, _, _, _ in rows}
    return codes, teams


def fill_provisional(season: int) -> None:
    """Add provisional quali/sprint rows for races where Jolpica has none yet."""
    init_fastf1()
    with get_session() as db:
        have_q = set(db.scalars(select(QualifyingResult.race_id).distinct()))
        have_s = set(db.scalars(select(Result.race_id).where(Result.session == "S").distinct()))
        sessions = db.execute(
            select(SessionRecord.race_id, SessionRecord.session, Race.round)
            .join(Race, Race.id == SessionRecord.race_id)
            .where(Race.season == season, SessionRecord.status == "ok")
        ).all()

    for race_id, code, round_ in sessions:
        if code == "Q" and race_id not in have_q:
            _provisional_quali(season, round_)
        elif code == "S" and race_id not in have_s:
            _provisional_sprint(season, round_)


def _load(season: int, round_: int, name: str):
    session = fastf1.get_session(season, round_, name)
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    return session


def _provisional_quali(season: int, round_: int) -> None:
    rid = jp.race_id(season, round_)
    q1, q2, q3 = _load(season, round_, "Qualifying").laps.split_qualifying_sessions()
    order = qualifying_order(q1, q2, q3)
    codes, teams = _driver_lookup(season, round_)
    rows = []
    for r in order.itertuples():
        drv = codes.get(r.Driver)
        if drv is None or drv not in teams:
            log.warning("%s: no driver id/team for %s; skipped", rid, r.Driver)
            continue
        rows.append(
            {"race_id": rid, "driver_id": drv, "constructor_id": teams[drv],
             "position": r.position, "q1_s": _f(r.q1_s), "q2_s": _f(r.q2_s), "q3_s": _f(r.q3_s),
             "source": "fastf1"}
        )  # fmt: skip
    with get_session() as db:
        upsert(db, QualifyingResult, rows, ["race_id", "driver_id"])
        db.commit()
    log.info("%s: provisional qualifying from FastF1 laps (%d drivers)", rid, len(rows))


def _provisional_sprint(season: int, round_: int) -> None:
    rid = jp.race_id(season, round_)
    order = sprint_order(_load(season, round_, "Sprint").laps)
    codes, teams = _driver_lookup(season, round_)
    rows = []
    for r in order.itertuples():
        drv = codes.get(r.Driver)
        if drv is None or drv not in teams:
            log.warning("%s: no driver id/team for %s; skipped", rid, r.Driver)
            continue
        pos = r.position_order if r.classified else None
        rows.append(
            {"race_id": rid, "session": "S", "driver_id": drv, "constructor_id": teams[drv],
             "car_number": None, "grid": None, "position": pos,
             "position_text": str(pos) if pos else "R", "position_order": r.position_order,
             "points": float(SPRINT_POINTS[pos - 1]) if pos and pos <= 8 else 0.0,
             "laps": int(r.laps), "status": "Provisional", "time_ms": None,
             "classified": bool(r.classified), "source": "fastf1"}
        )  # fmt: skip
    with get_session() as db:
        upsert(db, Result, rows, ["race_id", "session", "driver_id"])
        db.commit()
    log.info("%s: provisional sprint result from FastF1 laps (%d drivers)", rid, len(rows))


def _f(v) -> float | None:
    return None if pd.isna(v) else float(v)
