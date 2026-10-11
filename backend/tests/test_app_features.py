"""Ask the model, what-if scenarios and 'Beat the model', end to end through the API."""

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from f1p.api import simulation
from f1p.api.deps import get_db, get_now
from f1p.api.main import app
from f1p.pipeline import live

BEFORE_RACE = datetime(2026, 1, 1)


@pytest.fixture
def upcoming(db):
    """The mini DB with the last race (2026-4) turned back into an upcoming race.

    Qualifying stays, the race result is held back (returned for the test to publish), and a
    live post-qualifying prediction is made before the race.
    """
    result = pd.read_sql("select * from results where race_id = '2026-4' and session = 'R'", db)
    with db.begin() as c:
        c.execute(text("delete from results where race_id = '2026-4' and session = 'R'"))
    simulation._rows_cache.clear()
    simulation._model_cache.clear()
    live.predict("2026-4", "post", now=BEFORE_RACE, engine=db)
    now = {"t": BEFORE_RACE}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: now["t"]
    yield TestClient(app), db, result, now
    app.dependency_overrides.clear()
    simulation._rows_cache.clear()
    simulation._model_cache.clear()


def _publish(db, result):
    result.to_sql("results", db, if_exists="append", index=False)


def test_field_lists_drivers_in_grid_order(upcoming):
    client, *_ = upcoming
    f = client.get("/races/2026-4/field").json()
    assert f["grid_source"] == "qualifying" and not f["completed"]
    assert len(f["drivers"]) == 4
    assert {t["id"] for t in f["teams"]} == {"red", "blue"}


def test_questions_from_snapshot_are_consistent(upcoming):
    client, *_ = upcoming
    body = {
        "questions": [
            {"kind": "ahead", "driver": "alpha", "other": "bravo"},
            {"kind": "ahead", "driver": "bravo", "other": "alpha"},
            {"kind": "top_k", "driver": "alpha", "k": 4},
            {"kind": "team_wins", "team": "red"},
            {"kind": "team_wins", "team": "blue"},
            {"kind": "top_k", "driver": "nobody", "k": 1},
        ]
    }
    out = client.post("/races/2026-4/simulate", json=body).json()
    assert out["source"] == "snapshot" and out["snapshot_id"] is not None
    p = [a["probability"] for a in out["answers"]]
    assert p[0] + p[1] == pytest.approx(1)
    assert p[2] == pytest.approx(1)
    assert p[3] + p[4] == pytest.approx(1)
    assert out["answers"][5]["error"] and out["answers"][5]["probability"] is None
    assert all(a["happened"] is None for a in out["answers"])  # race not run yet
    # Same numbers as the saved prediction shows.
    snap = client.get("/races/2026-4/predictions?stage=post").json()
    by_id = {r["driver"]["id"]: r["p_win"] for r in out["rows"]}
    for r in snap["rows"]:
        assert by_id[r["driver"]["id"]] == pytest.approx(r["p_win"], abs=0.02)


def test_what_if_scenarios(upcoming):
    client, *_ = upcoming
    field = client.get("/races/2026-4/field").json()
    pole = field["drivers"][0]["id"]
    base = client.post("/races/2026-4/simulate", json={"scenario": {"chaos": 1.0}}).json()
    assert base["source"] == "snapshot"  # a no-op scenario uses the saved prediction

    worse = client.post(
        "/races/2026-4/simulate", json={"scenario": {"retire": [pole], "chaos": 1.0}}
    ).json()
    assert worse["source"] == "scenario"
    win = {r["driver"]["id"]: r["p_win"] for r in worse["rows"]}
    # A certain retirement can't win, except in the rare simulated race where every car in
    # this 4-car test field retires (someone is still listed first).
    assert win[pole] < 0.01
    assert sum(win.values()) == pytest.approx(1)

    out = client.post("/races/2026-4/simulate", json={"scenario": {"out": [pole]}}).json()
    assert len(out["rows"]) == 3 and pole not in out["grid"]

    reversed_grid = [d["id"] for d in reversed(field["drivers"])]
    out = client.post("/races/2026-4/simulate", json={"scenario": {"grid": reversed_grid}}).json()
    assert out["grid"] == reversed_grid

    assert (
        client.post("/races/2026-4/simulate", json={"scenario": {"grid": ["alpha"]}}).status_code
        == 422
    )
    assert client.post("/races/2026-4/simulate", json={"scenario": {"chaos": 9}}).status_code == 422
    assert client.post("/races/1999-1/simulate", json={}).status_code == 404


def test_what_if_refused_for_completed_races_but_questions_say_what_happened(upcoming):
    client, db, result, _ = upcoming
    _publish(db, result)
    r = client.post("/races/2026-4/simulate", json={"scenario": {"chaos": 2}})
    assert r.status_code == 409
    winner = result.sort_values("position_order")["driver_id"].iloc[0]
    out = client.post(
        "/races/2026-4/simulate",
        json={"questions": [{"kind": "top_k", "driver": winner, "k": 1}]},
    ).json()
    assert out["answers"][0]["happened"] is True


def test_beat_the_model_game(upcoming):
    client, db, result, now = upcoming
    assert client.post("/players", json={"nickname": "<bad>"}).status_code == 422
    r = client.post("/players", json={"nickname": "Lights Out"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert client.post("/players", json={"nickname": "lights out"}).status_code == 409
    auth = {"X-Player-Token": token}
    assert client.get("/players/me", headers=auth).json()["nickname"] == "Lights Out"
    assert client.get("/players/me", headers={"X-Player-Token": "nope"}).status_code == 401
    assert (
        client.put(
            "/races/2026-4/picks/me", json={"p1": "alpha", "p2": "bravo", "p3": "charlie"}
        ).status_code
        == 401
    )

    podium = list(result.sort_values("position_order")["driver_id"][:3])
    bad = client.put(
        "/races/2026-4/picks/me", headers=auth, json={"p1": "alpha", "p2": "alpha", "p3": "bravo"}
    )
    assert bad.status_code == 422
    pick = client.put("/races/2026-4/picks/me", headers=auth,
                      json={"p1": podium[0], "p2": podium[1], "p3": podium[2]})  # fmt: skip
    assert pick.status_code == 200 and pick.json()["locked"] is False

    summary = client.get("/races/2026-4/picks/summary").json()
    assert summary["n_players"] == 1 and summary["model_podium"] is None  # hidden until lock

    now["t"] = datetime(2027, 1, 1)  # race started: picks lock, model pick revealed
    locked = client.put("/races/2026-4/picks/me", headers=auth,
                        json={"p1": podium[1], "p2": podium[0], "p3": podium[2]})  # fmt: skip
    assert locked.status_code == 409
    assert client.get("/races/2026-4/picks/summary").json()["model_podium"] is not None

    _publish(db, result)
    mine = client.get("/races/2026-4/picks/me", headers=auth).json()
    assert mine["points"] == 40 and mine["locked"] is True
    history = client.get("/players/me/picks", headers=auth).json()
    assert len(history) == 1 and history[0]["points"] == 40
    assert [d["id"] for d in history[0]["actual_podium"]] == podium
    board = client.get("/leaderboard", params={"season": 2026}).json()
    assert board[0]["name"] == "Lights Out" and board[0]["points"] == 40 and board[0]["exact"] == 3
    assert any(e["is_model"] for e in board)
    summary = client.get("/races/2026-4/picks/summary").json()
    assert summary["crowd_avg_points"] == 40 and summary["model_points"] is not None
