from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from f1p.api import queries
from f1p.api.deps import get_db
from f1p.api.schemas import RaceDetail, RaceSummary, Snapshot, Stage

router = APIRouter(tags=["races"])


@router.get("/seasons", response_model=list[int])
def list_seasons(db: Engine = Depends(get_db)):
    return queries.seasons(db)


@router.get("/seasons/{year}/races", response_model=list[RaceSummary])
def season_races(year: int, db: Engine = Depends(get_db)):
    races = queries.race_summaries(db, season=year)
    if not races:
        raise HTTPException(404, f"No races for season {year}")
    return races


@router.get("/races/next", response_model=RaceSummary)
def next_race(db: Engine = Depends(get_db)):
    race = queries.next_race(db, datetime.now(timezone.utc).replace(tzinfo=None))
    if race is None:
        raise HTTPException(404, "No upcoming race")
    return race


@router.get("/races/{race_id}", response_model=RaceDetail)
def race(race_id: str, db: Engine = Depends(get_db)):
    detail = queries.race_detail(db, race_id)
    if detail is None:
        raise HTTPException(404, f"Unknown race {race_id}")
    return detail


@router.get("/races/{race_id}/predictions", response_model=Snapshot)
def race_prediction(
    race_id: str,
    stage: Stage | None = Query(None, description="Default: post if available, else pre."),
    db: Engine = Depends(get_db),
):
    """The latest prediction snapshot for a race and stage."""
    stages = [stage] if stage else ["post", "pre"]
    for st in stages:
        pid = queries.latest_snapshot_id(db, race_id, st)
        if pid is not None:
            return queries.snapshot(db, pid)
    raise HTTPException(404, f"No {stage or ''} prediction for {race_id}".replace("  ", " "))
