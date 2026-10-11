"""Feature correctness on a hand-built mini championship, plus point-in-time leakage tests."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from f1p import config
from f1p.features.build import build_features, feature_columns
from f1p.features.tables import prepare_tables, truncate_to

DRIVERS = ["alpha", "bravo", "charlie", "delta"]
TEAM = {"alpha": "red", "bravo": "red", "charlie": "blue", "delta": "blue"}
CODES = {"alpha": "ALP", "bravo": "BRA", "charlie": "CHA", "delta": "DEL"}


def _mini_tables(tmp_path, monkeypatch, sprint_round=3):
    """2 seasons x 4 rounds on 2 circuits. Finishing order rotates so form changes over time.

    Round ``sprint_round`` of season 2 is a sprint weekend (sprint before qualifying), with
    FP1 laps before the pre cutoff and Q laps after it. SQ laps lack driver ids, as in FastF1.
    """
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    races, results, quali, sessions = [], [], [], []
    rng = np.random.default_rng(0)
    for season in (2025, 2026):
        for rnd in range(1, 5):
            rid = f"{season}-{rnd}"
            race_day = datetime(season, 3, 1) + timedelta(weeks=2 * rnd)
            sprint = season == 2026 and rnd == sprint_round
            races.append(
                {
                    "id": rid, "season": season, "round": rnd, "name": f"GP {rid}",
                    "circuit_id": "monza" if rnd % 2 else "monaco", "circuit_name": "",
                    "locality": None, "country": None, "race_date": race_day.date(),
                    "race_start_utc": race_day + timedelta(hours=13),
                    "quali_start_utc": race_day - timedelta(hours=11),
                    "sprint_start_utc": race_day - timedelta(hours=15) if sprint else None,
                    "weekend_format": "sprint" if sprint else "conventional",
                }
            )  # fmt: skip
            order = list(rng.permutation(DRIVERS))
            for pos, d in enumerate(order, start=1):
                dnf = pos == 4 and rnd == 2
                results.append(
                    {
                        "race_id": rid, "session": "R", "driver_id": d, "constructor_id": TEAM[d],
                        "grid": 0 if (d == "delta" and rnd == 4) else pos,
                        "position": None if dnf else pos, "position_text": "R" if dnf else str(pos),
                        "position_order": pos, "points": float(10 - 2 * pos), "laps": 50,
                        "status": "Retired" if dnf else "Finished", "time_ms": None,
                        "classified": not dnf,
                    }
                )  # fmt: skip
                quali.append(
                    {"race_id": rid, "driver_id": d, "constructor_id": TEAM[d], "position": pos,
                     "q1_s": 80 + pos * 0.1, "q2_s": None, "q3_s": None}
                )  # fmt: skip
                if sprint:
                    results.append(
                        {"race_id": rid, "session": "S", "driver_id": d, "constructor_id": TEAM[d],
                         "grid": pos, "position": 5 - pos, "position_text": str(5 - pos),
                         "position_order": 5 - pos, "points": float(pos), "laps": 20,
                         "status": "Finished", "time_ms": None, "classified": True}
                    )  # fmt: skip
            if sprint:
                for code, offset, ids in (("FP1", -30, True), ("SQ", -26, False), ("Q", -11, True)):
                    path = f"laps/{rid}_{code}.parquet"
                    laps = _fake_laps(ids)
                    (tmp_path / "laps").mkdir(exist_ok=True)
                    laps.to_parquet(tmp_path / path)
                    sessions.append(
                        {"race_id": rid, "session": code, "status": "ok", "laps_path": path,
                         "start_utc": race_day + timedelta(hours=offset), "rainfall_frac": 0.0,
                         "track_temp": 40.0}
                    )  # fmt: skip

    drivers = pd.DataFrame({"id": DRIVERS, "code": [CODES[d] for d in DRIVERS]})
    sess_cols = ["race_id", "session", "status", "laps_path", "start_utc", "rainfall_frac",
                 "track_temp"]  # fmt: skip
    return prepare_tables(
        pd.DataFrame(races),
        pd.DataFrame(results),
        pd.DataFrame(quali),
        pd.DataFrame(sessions, columns=sess_cols),
        drivers,
    )


def _fake_laps(with_ids: bool) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(DRIVERS):  # alpha fastest, delta slowest
        for lap in range(1, 8):
            rows.append(
                {"Driver": CODES[d], "DriverId": d if with_ids else None, "Stint": 1.0,
                 "LapTimeS": 90 + i + 0.01 * lap, "Deleted": False, "PitInTimeS": np.nan,
                 "PitOutTimeS": np.nan if lap > 1 else 1.0, "TrackStatus": "1"}
            )  # fmt: skip
    return pd.DataFrame(rows)


@pytest.fixture
def mini(tmp_path, monkeypatch):
    return _mini_tables(tmp_path, monkeypatch)


def _row(df, race_id, driver):
    return df[(df.race_id == race_id) & (df.driver_id == driver)].iloc[0]


def test_one_row_per_entry_with_targets(mini):
    df = build_features("post", mini)
    assert len(df) == 8 * 4
    assert not df.duplicated(["race_id", "driver_id"]).any()
    assert set(feature_columns("post")) <= set(df.columns)
    assert df["finish_order"].notna().all()


def test_first_race_has_no_history(mini):
    df = build_features("pre", mini)
    first = df[df.race_id == "2025-1"]
    assert first["drv_form"].isna().all()
    assert (first["drv_starts"] == 0).all()
    assert (first["season_pts_before"] == 0).all()


def test_driver_form_is_ewm_of_prior_races(mini):
    df = build_features("pre", mini)
    t = mini
    r = t.results[(t.results.session == "R") & (t.results.driver_id == "alpha")]
    r = r.merge(t.races[["id", "race_idx"]], left_on="race_id", right_on="id").sort_values(
        "race_idx"
    )
    prior_pct = (r["position_order"].iloc[:3] - 1) / 3
    expected = prior_pct.ewm(halflife=4).mean().iloc[-1]
    assert _row(df, "2025-4", "alpha")["drv_form"] == pytest.approx(expected)


def test_championship_points_exclude_current_weekend(mini):
    df = build_features("pre", mini)
    t = mini
    pts = t.results[(t.results.driver_id == "bravo") & t.results.race_id.isin(["2026-1", "2026-2"])]
    assert _row(df, "2026-3", "bravo")["season_pts_before"] == pts["points"].sum()


def test_sprint_and_practice_known_pre_quali_but_quali_is_not(mini):
    pre = build_features("pre", mini)
    sprint = mini.results[(mini.results.race_id == "2026-3") & (mini.results.session == "S")]
    winner = sprint.loc[sprint.position_order == 1, "driver_id"].iloc[0]
    row = _row(pre, "2026-3", winner)
    assert row["sprint_weekend"] == 1.0
    assert row["sprint_pos_pct"] == pytest.approx(0.0)
    assert _row(pre, "2026-3", "delta")["fp_best_gap_pct"] > 0
    assert _row(pre, "2026-3", "alpha")["fp_best_gap_pct"] == 0
    # SQ laps had no driver ids; they are recovered from driver codes.
    assert _row(pre, "2026-3", "alpha")["sq_gap_pct"] == 0
    assert "quali_pos_pct" not in pre.columns


def test_pitlane_start_goes_to_back_of_grid(mini):
    post = build_features("post", mini)
    row = _row(post, "2025-4", "delta")
    assert row["pitlane_start"] == 1.0 and row["grid_pct"] == 1.0


@pytest.mark.parametrize("stage", ["pre", "post"])
def test_no_leakage_on_mini_data(mini, stage):
    """Features for race k must not change when everything after the cutoff is removed."""
    cols = feature_columns(stage)
    for race_id in mini.races["id"]:
        full = build_features(stage, mini, [race_id])[["driver_id", *cols]]
        asof = build_features(stage, truncate_to(mini, race_id, stage), [race_id])
        pd.testing.assert_frame_equal(full, asof[["driver_id", *cols]], check_dtype=False)


@pytest.mark.skipif(not config.DB_PATH.exists(), reason="needs the ingested database")
@pytest.mark.parametrize("stage", ["pre", "post"])
@pytest.mark.parametrize("race_id", ["2019-10", "2023-6", "2025-12", "2026-2", "2026-16"])
def test_no_leakage_on_real_data(stage, race_id):
    from f1p.features.tables import load_tables

    t = load_tables()
    cols = feature_columns(stage)
    full = build_features(stage, t, [race_id])[["driver_id", *cols]]
    asof = build_features(stage, truncate_to(t, race_id, stage), [race_id])
    pd.testing.assert_frame_equal(full, asof[["driver_id", *cols]], check_dtype=False)


def test_truncate_removes_future_and_blanks_target(mini):
    t = truncate_to(mini, "2025-3", "pre")
    assert t.results.race_id.isin(["2025-4", "2026-1"]).sum() == 0
    target = t.results[(t.results.race_id == "2025-3") & (t.results.session == "R")]
    assert target["position_order"].isna().all() and target["grid"].isna().all()
    assert "2025-3" not in set(t.qualifying.race_id)
