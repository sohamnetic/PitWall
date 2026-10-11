"""API endpoints against the temporary mini-championship database."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from f1p import config
from f1p.api.deps import get_db
from f1p.api.main import app
from f1p.api.queries import METRIC_KEYS
from f1p.pipeline import live


@pytest.fixture
def client(db):
    """Client over the test DB, with a scored post-quali snapshot and an unscored pre one."""
    after = datetime(2027, 1, 1)
    live.predict("2026-4", "post", now=after, engine=db)
    live.score_race("2026-4", db)
    live.predict("2026-4", "pre", now=after, engine=db)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_seasons_and_calendar(client):
    assert client.get("/seasons").json() == [2025, 2026]
    races = client.get("/seasons/2026/races").json()
    assert [r["id"] for r in races] == ["2026-1", "2026-2", "2026-3", "2026-4"]
    last = races[-1]
    assert last["status"] == "completed"
    assert last["latest_predictions"]["post"] is not None
    assert races[2]["weekend_format"] == "sprint"
    assert last["winner"]["id"] in {"alpha", "bravo", "charlie", "delta"}
    assert last["favourite"]["stage"] == "post"  # post-quali pick preferred over pre
    assert races[0]["favourite"] is None
    assert client.get("/seasons/1999/races").status_code == 404


def test_next_race_404_when_season_over(client):
    assert client.get("/races/next").status_code == 404


def test_race_detail(client):
    d = client.get("/races/2026-4").json()
    assert d["race"]["id"] == "2026-4"
    assert len(d["results"]) == 4 and d["results"][0]["position_order"] == 1
    assert len(d["qualifying"]) == 4
    assert {s["stage"] for s in d["snapshots"]} == {"pre", "post"}
    assert d["results"][0]["driver"]["team_name"] in {"red", "blue"}
    assert client.get("/races/1999-1").status_code == 404


def test_prediction_snapshot_with_score(client):
    snap = client.get("/races/2026-4/predictions", params={"stage": "post"}).json()
    assert snap["stage"] == "post" and snap["made_before_cutoff"] is False
    assert len(snap["rows"]) == 4
    assert sum(r["p_win"] for r in snap["rows"]) == pytest.approx(1, abs=1e-4)
    assert all(len(r["position_probs"]) == 4 for r in snap["rows"])
    assert all(r["actual_position"] in {1, 2, 3, 4} for r in snap["rows"])
    assert snap["score"]["baseline_name"] == "grid"
    assert set(snap["score"]["model"]) == set(METRIC_KEYS)
    # Default stage is post when it exists; the pre snapshot is unscored.
    assert client.get("/races/2026-4/predictions").json()["id"] == snap["id"]
    pre = client.get("/races/2026-4/predictions", params={"stage": "pre"}).json()
    assert pre["score"] is None and pre["scored"] is False
    assert client.get(f"/predictions/{pre['id']}").json()["id"] == pre["id"]
    assert client.get("/predictions/9999").status_code == 404
    assert client.get("/races/2025-1/predictions").status_code == 404


def test_performance_reads_backtest_files(client):
    perf = client.get("/performance").json()
    assert perf["backtest"] == {}  # no backtest files yet
    assert len(perf["track_record"]) == 2

    out = config.DATA_DIR / "backtest"
    out.mkdir(parents=True)
    rng = np.random.default_rng(0)
    races = pd.DataFrame(
        [{"model": m, "race_id": f"r{i}", "season": 2025 + i % 2,
          **{k: float(rng.random()) for k in METRIC_KEYS}}
         for m in ("model", "grid") for i in range(6)]
    )  # fmt: skip
    races.to_parquet(out / "post_races.parquet")
    drivers = pd.DataFrame(
        {"model": "model", "p_win": rng.random(50), "p_podium": rng.random(50),
         "p_points": rng.random(50), "won": rng.integers(0, 2, 50).astype(float),
         "podium": rng.integers(0, 2, 50).astype(float),
         "in_points": rng.integers(0, 2, 50).astype(float)}
    )  # fmt: skip
    drivers.to_parquet(out / "post_drivers.parquet")

    perf = client.get("/performance").json()
    post = perf["backtest"]["post"]
    assert {s["model"] for s in post["summary"]} == {"model", "grid"}
    assert {(p["model"], p["season"]) for p in post["by_season"]} == {
        ("model", 2025),
        ("model", 2026),
        ("grid", 2025),
        ("grid", 2026),
    }
    assert set(post["calibration"]) == {"win", "podium", "points"}


def test_drivers(client):
    drivers = client.get("/drivers", params={"season": 2026}).json()
    assert {d["id"] for d in drivers} == {"alpha", "bravo", "charlie", "delta"}
    d = client.get("/drivers/alpha", params={"season": 2026}).json()
    assert d["driver"]["team_id"] == "red"
    assert len(d["recent_results"]) == 8
    assert d["season_points"] > 0
    assert {p["stage"] for p in d["predictions"]} == {"pre", "post"}
    assert client.get("/drivers/nobody").status_code == 404


def test_openapi_docs(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/races/next",
        "/races/{race_id}/predictions",
        "/performance",
        "/drivers/{driver_id}",
    ):
        assert p in paths
