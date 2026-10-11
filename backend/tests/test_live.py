"""Live pipeline: provisional classifications, race resolution, predict -> score round trip."""

from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import func, select

from f1p.data.db import get_session
from f1p.data.models import (
    Prediction,
    PredictionScore,
)
from f1p.data.provisional import qualifying_order, sprint_order
from f1p.features.tables import prepare_tables
from f1p.pipeline import live
from tests.test_features import _mini_tables


def _laps(rows):
    return pd.DataFrame(rows, columns=["Driver", "LapTime", "Deleted"]).assign(
        LapTime=lambda d: pd.to_timedelta(d["LapTime"], unit="s")
    )


def test_qualifying_order_ranks_by_furthest_segment():
    q1 = _laps([("A", 90.0, False), ("B", 89.0, False), ("C", 91.0, False), ("D", 88.0, True)])
    q2 = _laps([("A", 89.5, False), ("B", 89.9, False), ("C", 89.0, False)])
    q3 = _laps([("A", 89.2, False), ("B", 88.9, False)])
    order = qualifying_order(q1, q2, q3)
    # B and A reached Q3 (B faster there); C out in Q2; D's only lap was deleted.
    assert order["Driver"].tolist() == ["B", "A", "C", "D"]
    assert order.loc[order.Driver == "D", "q1_s"].isna().all()


def test_sprint_order_puts_retirements_last():
    laps = pd.DataFrame(
        {"Driver": ["A", "A", "B", "B", "C"], "LapNumber": [1, 20, 1, 20, 5],
         "Position": [2, 2, 1, 1, 3]}
    )  # fmt: skip
    order = sprint_order(laps)
    assert order["Driver"].tolist() == ["B", "A", "C"]
    assert order["classified"].tolist() == [True, True, False]


def test_resolve_race_and_auto_stage(tmp_path, monkeypatch):
    t = _mini_tables(tmp_path, monkeypatch)
    now = datetime(2027, 1, 1)
    assert live.resolve_race(t, "last", now) == "2026-4"
    with pytest.raises(ValueError):
        live.resolve_race(t, "next", now)  # season over
    assert live.resolve_race(t, "2025-2", now) == "2025-2"
    # Remove 2026-4's result and qualifying: it becomes the next race, at the pre stage.
    t2 = prepare_tables(
        t.races.drop(columns=["race_idx", "regs_era", "pre_cutoff", "post_cutoff", "sprint_start"]),
        t.results[t.results.race_id != "2026-4"],
        t.qualifying[t.qualifying.race_id != "2026-4"],
        t.sessions,
        t.drivers,
    )
    assert live.resolve_race(t2, "next", datetime(2026, 1, 1)) == "2026-4"
    assert live.auto_stage(t2, "2026-4") == "pre"
    assert live.auto_stage(t, "2026-4") == "post"


def test_predict_then_score_round_trip(db):
    now = datetime(2027, 1, 1)  # after the race: a backfill
    pid = live.predict("2026-4", "post", now=now, engine=db)
    snap = live.load_snapshot(pid, db)
    assert snap.prediction.made_before_cutoff is False
    assert len(snap.rows) == 4
    assert snap.rows["p_win"].sum() == pytest.approx(1.0, abs=1e-6)
    assert sorted(snap.rows["pred_rank"]) == [1, 2, 3, 4]

    # Snapshots are immutable: predicting again adds a new one.
    pid2 = live.predict("2026-4", "post", now=now, engine=db)
    assert pid2 != pid

    scored = live.score_race("2026-4", db)
    assert sorted(scored) == sorted([pid, pid2])
    assert live.score_race("2026-4", db) == []  # nothing left to score
    with get_session(db) as s:
        assert s.scalar(select(func.count()).select_from(PredictionScore)) == 2
        assert s.scalar(select(func.count()).select_from(Prediction)) == 2
    rec = live.track_record(db)
    assert rec["spearman"].notna().all() and rec["base_spearman"].notna().all()
    assert set(rec["baseline_name"]) == {"grid"}
