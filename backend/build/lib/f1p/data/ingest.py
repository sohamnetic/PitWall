"""Incremental, idempotent ingest of results (Jolpica) and lap data (FastF1)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from fastf1.req import RateLimitExceededError
from sqlalchemy import delete, select

from f1p import config
from f1p.data import fastf1_loader as ff
from f1p.data import jolpica as jp
from f1p.data.db import get_session, upsert
from f1p.data.models import (
    Constructor,
    Driver,
    QualifyingResult,
    Race,
    Result,
    SessionRecord,
)

log = logging.getLogger(__name__)

# A session's timing data is usually published within an hour or two of the chequered flag.
SESSION_DATA_DELAY = timedelta(hours=4)
RATE_LIMIT_SLEEP_S = 5 * 60
TIMING_HOST = "https://livetiming.formula1.com/static/"


def _timing_reachable() -> bool:
    """FastF1 logs network failures and returns no laps, which looks like a session without
    data. Only trust "no data" when F1's timing server actually answers."""
    import requests

    try:
        return requests.head(TIMING_HOST, timeout=10).status_code < 500
    except requests.RequestException:
        return False


def parse_seasons(spec: str) -> list[int]:
    """'2024' -> [2024]; '2018-2020' -> [2018, 2019, 2020]; '2019,2021' -> [2019, 2021]."""
    seasons: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            seasons.update(range(lo, hi + 1))
        elif part:
            seasons.add(int(part))
    return sorted(seasons)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ingest_results(seasons: list[int]) -> None:
    """Calendar, race and sprint classifications, and qualifying for each season."""
    for season in seasons:
        schedule = jp.fetch_schedule(season)
        results = jp.fetch_results(season)
        sprints = jp.fetch_sprint_results(season) if season >= 2021 else []
        qualifying = jp.fetch_qualifying(season)

        drivers, constructors = {}, {}
        for race in results + sprints + qualifying:
            for row in (
                race.get("Results", [])
                + race.get("SprintResults", [])
                + race.get("QualifyingResults", [])
            ):
                drivers[row["Driver"]["driverId"]] = jp.parse_driver(row["Driver"])
                cons = row["Constructor"]
                constructors[cons["constructorId"]] = jp.parse_constructor(cons)

        result_rows = [r for race in results for r in jp.parse_result_rows(race, "R")]
        result_rows += [r for race in sprints for r in jp.parse_result_rows(race, "S")]
        quali_rows = [q for race in qualifying for q in jp.parse_qualifying_rows(race)]

        with get_session() as db:
            upsert(db, Race, [jp.parse_race(r) for r in schedule], ["id"])
            upsert(db, Driver, drivers.values(), ["id"])
            upsert(db, Constructor, constructors.values(), ["id"])
            # Official rows supersede provisional FastF1-derived ones for the same session.
            for session_code, rows in (("R", result_rows), ("S", result_rows)):
                official = {r["race_id"] for r in rows if r["session"] == session_code}
                db.execute(
                    delete(Result).where(
                        Result.race_id.in_(official),
                        Result.session == session_code,
                        Result.source == "fastf1",
                    )
                )
            db.execute(
                delete(QualifyingResult).where(
                    QualifyingResult.race_id.in_({q["race_id"] for q in quali_rows}),
                    QualifyingResult.source == "fastf1",
                )
            )
            upsert(db, Result, result_rows, ["race_id", "session", "driver_id"])
            upsert(db, QualifyingResult, quali_rows, ["race_id", "driver_id"])
            db.commit()
        log.info(
            "%s: %d races scheduled, %d with results, %d result rows, %d quali rows",
            season,
            len(schedule),
            len(results),
            len(result_rows),
            len(quali_rows),
        )


def ingest_laps(
    seasons: list[int], sessions: tuple[str, ...] = ff.SESSION_CODES, force: bool = False
) -> None:
    """Download lap data for every finished session not already stored. Newest seasons first."""
    now = _utcnow()
    for season in sorted(seasons, reverse=True):
        scheduled = [s for s in ff.season_sessions(season) if s.code in sessions]
        with get_session() as db:
            known_races = set(db.scalars(select(Race.id).where(Race.season == season)))
            done = {
                (r.race_id, r.session)
                for r in db.scalars(select(SessionRecord))
                if r.status in ("ok", "no_data") and r.race_id in known_races
            }

        todo = []
        for s in scheduled:
            rid = jp.race_id(s.season, s.round)
            if rid not in known_races:
                log.warning("%s %s: race not in results DB, run results ingest first", rid, s.code)
                continue
            if s.start_utc is None or s.start_utc.to_pydatetime() + SESSION_DATA_DELAY > now:
                continue
            if not force and (rid, s.code) in done:
                continue
            todo.append(s)

        log.info("%s: %d sessions to fetch", season, len(todo))
        for i, s in enumerate(todo, start=1):
            _ingest_one_session(s)
            log.info("%s: %d/%d done (round %d %s)", season, i, len(todo), s.round, s.code)


def _ingest_one_session(s: ff.ScheduledSession) -> None:
    rid = jp.race_id(s.season, s.round)
    record = {
        "race_id": rid,
        "session": s.code,
        "start_utc": s.start_utc.to_pydatetime() if s.start_utc is not None else None,
        "error": None,
        "n_laps": None,
        "laps_path": None,
        "air_temp": None,
        "track_temp": None,
        "humidity": None,
        "wind_speed": None,
        "rainfall_frac": None,
    }
    while True:
        try:
            laps, weather = ff.load_session(s)
            break
        except RateLimitExceededError:
            log.warning("FastF1 rate limit hit; sleeping %d min", RATE_LIMIT_SLEEP_S // 60)
            time.sleep(RATE_LIMIT_SLEEP_S)
        except Exception as exc:  # noqa: BLE001 - record and move on; retried next run
            log.error("%s %s failed: %s", rid, s.code, exc)
            record.update(status="error", error=str(exc)[:500])
            _save_record(record)
            return

    if laps.empty and not _timing_reachable():
        log.error("%s %s: no laps and the timing server is unreachable; will retry", rid, s.code)
        record.update(status="error", error="timing server unreachable")
    elif laps.empty:
        record["status"] = "no_data"
    else:
        path = ff.laps_path(s.season, s.round, s.code)
        path.parent.mkdir(parents=True, exist_ok=True)
        laps.to_parquet(path, index=False)
        record.update(
            status="ok",
            n_laps=len(laps),
            laps_path=str(path.relative_to(config.DATA_DIR)),
            **weather,
        )
    _save_record(record)


def _save_record(record: dict) -> None:
    record["fetched_at"] = _utcnow()
    with get_session() as db:
        upsert(db, SessionRecord, [record], ["race_id", "session"])
        db.commit()
