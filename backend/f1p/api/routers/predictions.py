from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from f1p.api import queries
from f1p.api.deps import get_db
from f1p.api.schemas import DriverDetail, DriverRef, Performance, Snapshot

router = APIRouter()


@router.get("/predictions/{prediction_id}", response_model=Snapshot, tags=["predictions"])
def prediction(prediction_id: int, db: Engine = Depends(get_db)):
    snap = queries.snapshot(db, prediction_id)
    if snap is None:
        raise HTTPException(404, f"Unknown prediction {prediction_id}")
    return snap


@router.get("/performance", response_model=Performance, tags=["performance"])
def performance(db: Engine = Depends(get_db)):
    """Walk-forward backtest summary, calibration, and the live track record."""
    return queries.performance(db)


def _current_season() -> int:
    return datetime.now(timezone.utc).year


@router.get("/drivers", response_model=list[DriverRef], tags=["drivers"])
def drivers(season: int | None = Query(None), db: Engine = Depends(get_db)):
    return queries.season_drivers(db, season or _current_season())


@router.get("/drivers/{driver_id}", response_model=DriverDetail, tags=["drivers"])
def driver(driver_id: str, season: int | None = Query(None), db: Engine = Depends(get_db)):
    detail = queries.driver_detail(db, driver_id, season or _current_season())
    if detail is None:
        raise HTTPException(404, f"Unknown driver {driver_id}")
    return detail
