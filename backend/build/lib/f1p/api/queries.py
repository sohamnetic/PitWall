"""Read-only queries behind the API. Every function takes an engine and returns plain dicts."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
from sqlalchemy import Engine, text

from f1p import config
from f1p.eval.metrics import calibration_table

METRIC_KEYS = [
    "spearman", "pos_mae", "winner_hit", "top3_hit", "top10_hit", "win_logloss", "win_brier",
    "podium_logloss", "podium_brier", "points_logloss", "points_brier",
]  # fmt: skip


def _df(engine: Engine, sql: str, **params) -> pd.DataFrame:
    return pd.read_sql(text(sql), engine, params=params)


def _none(v):
    """NaN/NaT -> None, numpy scalars -> Python."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _none(v) for k, v in row.items()} for row in df.to_dict("records")]


# ------------------------------------------------------------------------------- drivers


def driver_refs(engine: Engine) -> dict[str, dict]:
    d = _df(
        engine,
        "select id, code, permanent_number as number, "
        "given_name || ' ' || family_name as name from drivers",
    )
    return {
        r["id"]: {"id": r["id"], "code": r["code"], "name": r["name"], "number": r["number"]}
        for r in _records(d)
    }


def team_names(engine: Engine) -> dict[str, str]:
    t = _df(engine, "select id, name from constructors")
    return dict(zip(t["id"], t["name"], strict=True))


def driver_ref(refs, teams, driver_id, team_id=None) -> dict:
    base = refs.get(driver_id, {"id": driver_id, "code": None, "name": driver_id, "number": None})
    return {**base, "team_id": team_id, "team_name": teams.get(team_id) if team_id else None}


# --------------------------------------------------------------------------------- races


def seasons(engine: Engine) -> list[int]:
    return [
        int(s) for s in _df(engine, "select distinct season from races order by season")["season"]
    ]


def race_summaries(
    engine: Engine, season: int | None = None, race_id: str | None = None
) -> list[dict]:
    where, params = [], {}
    if season is not None:
        where.append("ra.season = :season")
        params["season"] = season
    if race_id is not None:
        where.append("ra.id = :race_id")
        params["race_id"] = race_id
    sql = f"""
        select ra.*,
          (select count(*) from results r where r.race_id = ra.id and r.session = 'R'
             and coalesce(r.source, 'jolpica') = 'jolpica') as n_official,
          (select count(*) from qualifying q where q.race_id = ra.id
             and coalesce(q.source, 'jolpica') = 'jolpica') as n_quali_official,
          (select count(*) from qualifying q where q.race_id = ra.id) as n_quali,
          (select max(id) from predictions p
             where p.race_id = ra.id and p.stage = 'pre') as pre_id,
          (select max(id) from predictions p
             where p.race_id = ra.id and p.stage = 'post') as post_id
        from races ra
        {"where " + " and ".join(where) if where else ""}
        order by ra.season, ra.round
    """  # only the fixed WHERE fragments above are interpolated; values are bound parameters
    refs, teams = driver_refs(engine), team_names(engine)
    winners = {
        r["race_id"]: driver_ref(refs, teams, r["driver_id"], r["constructor_id"])
        for r in _records(
            _df(engine, "select race_id, driver_id, constructor_id from results "
                        "where session = 'R' and position_order = 1")
        )
    }  # fmt: skip
    picks = _records(
        _df(
            engine,
            """select p.race_id, p.stage, p.made_before_cutoff, pr.driver_id, pr.constructor_id,
                      pr.p_win
               from predictions p join prediction_rows pr on pr.prediction_id = p.id
               where pr.pred_rank = 1
                 and p.id = (select max(id) from predictions p2
                             where p2.race_id = p.race_id and p2.stage = p.stage)""",
        )
    )
    favourites: dict[str, dict] = {}
    for f in picks:
        # Post-qualifying pick is preferred; a pre pick only fills in when there is no post.
        if f["stage"] == "pre" and f["race_id"] in favourites:
            continue
        favourites[f["race_id"]] = {
            "driver": driver_ref(refs, teams, f["driver_id"], f["constructor_id"]),
            "p_win": f["p_win"],
            "stage": f["stage"],
            "live": bool(f["made_before_cutoff"]),
        }
    out = []
    for r in _records(_df(engine, sql, **params)):
        out.append(
            {
                **{
                    k: r[k]
                    for k in (
                        "id",
                        "season",
                        "round",
                        "name",
                        "circuit_id",
                        "circuit_name",
                        "locality",
                        "country",
                        "race_date",
                        "race_start_utc",
                        "quali_start_utc",
                        "weekend_format",
                    )
                },  # fmt: skip
                "status": "completed" if r["n_official"] else "upcoming",
                "result_source": "official" if r["n_official"] else "none",
                "qualifying_source": (
                    "official"
                    if r["n_quali_official"]
                    else "provisional"
                    if r["n_quali"]
                    else "none"
                ),
                "latest_predictions": {"pre": r["pre_id"], "post": r["post_id"]},
                "winner": winners.get(r["id"]) if r["n_official"] else None,
                "favourite": favourites.get(r["id"]),
            }
        )
    return out


def next_race(engine: Engine, now: datetime) -> dict | None:
    """The first race without an official result whose start is not long past."""
    cutoff = now - pd.Timedelta(hours=3)
    for race in race_summaries(engine):
        start = race["race_start_utc"] or pd.Timestamp(race["race_date"])
        if race["status"] == "upcoming" and pd.Timestamp(start) > cutoff:
            return race
    return None


def _results(engine: Engine, race_id: str, session: str, refs, teams) -> list[dict]:
    df = _df(
        engine,
        "select * from results where race_id = :race_id and session = :session "
        "order by position_order",
        race_id=race_id,
        session=session,
    )
    return [
        {
            "driver": driver_ref(refs, teams, r["driver_id"], r["constructor_id"]),
            **{
                k: r[k]
                for k in (
                    "grid",
                    "position",
                    "position_text",
                    "position_order",
                    "points",
                    "laps",
                    "status",
                    "source",
                )
            },  # fmt: skip
        }
        for r in _records(df)
    ]


def race_detail(engine: Engine, race_id: str) -> dict | None:
    races = race_summaries(engine, race_id=race_id)
    if not races:
        return None
    refs, teams = driver_refs(engine), team_names(engine)
    q = _df(engine, "select * from qualifying where race_id = :r order by position", r=race_id)
    return {
        "race": races[0],
        "snapshots": snapshot_metas(engine, race_id),
        "results": _results(engine, race_id, "R", refs, teams),
        "sprint": _results(engine, race_id, "S", refs, teams),
        "qualifying": [
            {
                "driver": driver_ref(refs, teams, r["driver_id"], r["constructor_id"]),
                **{k: r[k] for k in ("position", "q1_s", "q2_s", "q3_s", "source")},
            }
            for r in _records(q)
        ],  # fmt: skip
    }


# --------------------------------------------------------------------------- predictions


_META_SQL = """
    select p.*, (s.prediction_id is not null) as scored
    from predictions p left join prediction_scores s on s.prediction_id = p.id
"""


def _meta(r: dict) -> dict:
    return {
        **{k: r[k] for k in ("id", "race_id", "stage", "created_at", "cutoff_utc",
                             "model_trained_through", "temperature", "model_version")},
        "made_before_cutoff": bool(r["made_before_cutoff"]),
        "scored": bool(r["scored"]),
    }  # fmt: skip


def snapshot_metas(engine: Engine, race_id: str) -> list[dict]:
    df = _df(engine, _META_SQL + " where p.race_id = :r order by p.id", r=race_id)
    return [_meta(r) for r in _records(df)]


def latest_snapshot_id(engine: Engine, race_id: str, stage: str) -> int | None:
    df = _df(
        engine,
        "select max(id) as id from predictions where race_id = :r and stage = :s",
        r=race_id,
        s=stage,
    )
    return _none(df["id"].iloc[0])


def snapshot(engine: Engine, prediction_id: int) -> dict | None:
    meta = _df(engine, _META_SQL + " where p.id = :i", i=prediction_id)
    if meta.empty:
        return None
    m = _records(meta)[0]
    refs, teams = driver_refs(engine), team_names(engine)
    rows = _df(
        engine,
        "select * from prediction_rows where prediction_id = :i order by pred_rank",
        i=prediction_id,
    )
    actual = _df(
        engine,
        "select driver_id, position_order from results where race_id = :r and session = 'R'",
        r=m["race_id"],
    ).set_index("driver_id")["position_order"]
    out_rows = [
        {
            "driver": driver_ref(refs, teams, r["driver_id"], r["constructor_id"]),
            **{k: r[k] for k in ("pred_rank", "expected_pos", "p_win", "p_podium", "p_points")},
            "position_probs": json.loads(r["position_probs"]),
            "actual_position": _none(actual.get(r["driver_id"])),
        }
        for r in _records(rows)
    ]
    return {**_meta(m), "rows": out_rows, "score": _score(engine, prediction_id)}


def _score(engine: Engine, prediction_id: int) -> dict | None:
    df = _df(engine, "select * from prediction_scores where prediction_id = :i", i=prediction_id)
    if df.empty:
        return None
    s = _records(df)[0]
    return {
        "scored_at": s["scored_at"],
        "n_drivers": s["n_drivers"],
        "model": {k: s[k] for k in METRIC_KEYS},
        "baseline_name": s["baseline_name"],
        "baseline": json.loads(s["baseline_metrics"]),
    }


# --------------------------------------------------------------------------- performance


# The "obvious guess" a fan would make, per stage: the comparison on the plain-English page.
PLAIN_BASELINE = {"post": "grid", "pre": "championship"}
HONESTY_BANDS = [0.0, 0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0]


def _plain(stage: str, races: pd.DataFrame, drivers: pd.DataFrame | None) -> dict | None:
    """The backtest in everyday terms: model vs the obvious guess, race by race."""
    base = PLAIN_BASELINE[stage]
    m = races[races["model"] == "model"].set_index("race_id")
    b = races[races["model"] == base].set_index("race_id").reindex(m.index)
    if m.empty or b["spearman"].isna().all():
        return None
    diff = m["spearman"] - b["spearman"]

    def h2h(d: pd.Series) -> dict:
        return {
            "model": int((d > 1e-9).sum()),
            "baseline": int((d < -1e-9).sum()),
            "tie": int((d.abs() <= 1e-9).sum()),
        }

    seasons = []
    for season, idx in m.groupby("season").groups.items():
        seasons.append(
            {
                "season": int(season),
                "races": len(idx),
                **{f"h2h_{k}": v for k, v in h2h(diff.loc[idx]).items()},
                "model_winners": int(m.loc[idx, "winner_hit"].sum()),
                "baseline_winners": int(b.loc[idx, "winner_hit"].sum()),
                "model_order": float(m.loc[idx, "spearman"].mean()),
                "baseline_order": float(b.loc[idx, "spearman"].mean()),
            }
        )

    honesty = []
    if drivers is not None:
        d = drivers[drivers["model"] == "model"]
        said = pd.concat([d["p_win"], d["p_podium"], d["p_points"]], ignore_index=True)
        happened = pd.concat([d["won"], d["podium"], d["in_points"]], ignore_index=True)
        band = pd.cut(said, HONESTY_BANDS, include_lowest=True)
        t = pd.DataFrame({"said": said, "happened": happened, "band": band})
        for interval, g in t.groupby("band", observed=True):
            honesty.append(
                {
                    "low": float(interval.left if interval.left > 0 else 0.0),
                    "high": float(interval.right),
                    "said": float(g["said"].mean()),
                    "happened": float(g["happened"].mean()),
                    "n": len(g),
                }
            )

    return {
        "baseline": base,
        "races": len(m),
        "head_to_head": h2h(diff),
        "winners": {"model": int(m["winner_hit"].sum()), "baseline": int(b["winner_hit"].sum())},
        "podium_drivers": {
            "model": float(m["top3_hit"].mean() * 3),
            "baseline": float(b["top3_hit"].mean() * 3),
        },
        "avg_miss": {"model": float(m["pos_mae"].mean()), "baseline": float(b["pos_mae"].mean())},
        "seasons": seasons,
        "honesty": honesty,
    }


def _backtest(stage: str) -> dict | None:
    races_path = config.DATA_DIR / "backtest" / f"{stage}_races.parquet"
    drivers_path = config.DATA_DIR / "backtest" / f"{stage}_drivers.parquet"
    if not races_path.exists():
        return None
    races = pd.read_parquet(races_path)
    summary = races.groupby("model")[METRIC_KEYS].mean().sort_values("spearman", ascending=False)
    counts = races.groupby("model").size()
    by_season = races.groupby(["model", "season"])[["spearman", "win_logloss"]].mean()

    calibration = {}
    all_drivers = pd.read_parquet(drivers_path) if drivers_path.exists() else None
    if all_drivers is not None:
        d = all_drivers[all_drivers["model"] == "model"]
        for name, prob, outcome in (("win", "p_win", "won"), ("podium", "p_podium", "podium"),
                                    ("points", "p_points", "in_points")):  # fmt: skip
            t = calibration_table(d, prob, outcome, bins=10)
            calibration[name] = _records(t[["predicted", "observed", "n"]])
    return {
        "summary": [
            {"model": m, "races": int(counts[m]), "metrics": {k: float(v) for k, v in row.items()}}
            for m, row in summary.iterrows()
        ],
        "by_season": [
            {"model": m, "season": int(s), **{k: float(v) for k, v in row.items()}}
            for (m, s), row in by_season.iterrows()
        ],
        "calibration": calibration,
        "plain": _plain(stage, races, all_drivers),
    }


def track_record(engine: Engine) -> list[dict]:
    df = _df(
        engine,
        """select p.id, p.race_id, r.name, p.stage, p.created_at, p.made_before_cutoff,
                  s.spearman, s.winner_hit, s.win_logloss, s.baseline_name, s.baseline_metrics
           from predictions p
           join races r on r.id = p.race_id
           left join prediction_scores s on s.prediction_id = p.id
           order by r.season, r.round, p.id""",
    )
    picks = _df(
        engine,
        """select prediction_id, driver_id, constructor_id, p_win from prediction_rows
           where pred_rank = 1""",
    ).set_index("prediction_id")
    winners = _df(
        engine,
        """select race_id, driver_id, constructor_id from results
           where session = 'R' and position_order = 1
             and coalesce(source, 'jolpica') = 'jolpica'""",
    ).set_index("race_id")
    refs, teams = driver_refs(engine), team_names(engine)
    out = []
    for r in _records(df):
        base = json.loads(r["baseline_metrics"]) if r["baseline_metrics"] else {}
        pick = picks.loc[r["id"]] if r["id"] in picks.index else None
        won = winners.loc[r["race_id"]] if r["race_id"] in winners.index else None
        out.append(
            {
                "snapshot_id": r["id"], "race_id": r["race_id"], "race_name": r["name"],
                "stage": r["stage"], "created_at": r["created_at"],
                "live": bool(r["made_before_cutoff"]), "spearman": r["spearman"],
                "winner_hit": r["winner_hit"], "win_logloss": r["win_logloss"],
                "baseline_name": r["baseline_name"],
                "baseline_spearman": base.get("spearman"),
                "baseline_win_logloss": base.get("win_logloss"),
                "pick": None if pick is None else driver_ref(
                    refs, teams, pick["driver_id"], pick["constructor_id"]),
                "pick_p_win": None if pick is None else float(pick["p_win"]),
                "winner": None if won is None else driver_ref(
                    refs, teams, won["driver_id"], won["constructor_id"]),
            }
        )  # fmt: skip
    return out


def performance(engine: Engine) -> dict:
    backtest = {st: bt for st in ("pre", "post") if (bt := _backtest(st)) is not None}
    return {"backtest": backtest, "track_record": track_record(engine)}


# ------------------------------------------------------------------------------- drivers


def season_drivers(engine: Engine, season: int) -> list[dict]:
    """Drivers who raced in ``season``, with their latest team."""
    df = _df(
        engine,
        """select r.driver_id, r.constructor_id from results r
           join races ra on ra.id = r.race_id
           where ra.season = :s and r.session = 'R'
           order by ra.round""",
        s=season,
    )
    latest = df.groupby("driver_id")["constructor_id"].last()
    refs, teams = driver_refs(engine), team_names(engine)
    out = [driver_ref(refs, teams, d, c) for d, c in latest.items()]
    return sorted(out, key=lambda r: (r["team_name"] or "", r["name"]))


def driver_detail(engine: Engine, driver_id: str, season: int, n_recent: int = 10) -> dict | None:
    refs, teams = driver_refs(engine), team_names(engine)
    if driver_id not in refs:
        return None
    nat = _df(engine, "select nationality from drivers where id = :d", d=driver_id)
    res = _df(
        engine,
        """select r.race_id, ra.name as race_name, ra.season, r.constructor_id as team_id,
                  r.grid, q.position as quali_position, r.position, r.position_text, r.points
           from results r
           join races ra on ra.id = r.race_id
           left join qualifying q on q.race_id = r.race_id and q.driver_id = r.driver_id
           where r.driver_id = :d and r.session = 'R'
           order by ra.season desc, ra.round desc""",
        d=driver_id,
    )
    pts = _df(
        engine,
        """select coalesce(sum(r.points), 0) as pts from results r
           join races ra on ra.id = r.race_id where r.driver_id = :d and ra.season = :s""",
        d=driver_id,
        s=season,
    )["pts"].iloc[0]
    preds = _df(
        engine,
        """select p.id as snapshot_id, p.race_id, p.stage, pr.pred_rank, pr.p_win, pr.p_podium,
                  res.position_order as actual_position
           from prediction_rows pr
           join predictions p on p.id = pr.prediction_id
           left join results res on res.race_id = p.race_id and res.driver_id = pr.driver_id
                and res.session = 'R'
           where pr.driver_id = :d
           order by p.id desc""",
        d=driver_id,
    )
    team = res["team_id"].iloc[0] if not res.empty else None
    recent = res.head(n_recent).drop(columns="season")
    return {
        "driver": driver_ref(refs, teams, driver_id, team),
        "nationality": _none(nat["nationality"].iloc[0]),
        "season": season,
        "season_points": float(pts),
        "recent_results": _records(recent),
        "predictions": _records(preds),
    }


# ----------------------------------------------------------------------------- standings


def _max_points(season: int) -> tuple[int, int, int, int]:
    """Most points one driver / one team can score from a Grand Prix and from a sprint."""
    fastest_lap = 1 if 2019 <= season <= 2024 else 0
    sprint_driver, sprint_team = (8, 15) if season >= 2022 else (3, 5) if season == 2021 else (0, 0)
    return 25 + fastest_lap, 25 + 18 + fastest_lap, sprint_driver, sprint_team


def _ranked(df: pd.DataFrame, key: str, gp: pd.DataFrame) -> pd.DataFrame:
    """Order by points, ties broken by countback (most wins, then most seconds, ...)."""
    counts = gp.pivot_table(index=key, columns="position", values="round", aggfunc="count")
    counts = counts.reindex(df.index).fillna(0)
    order = df[["points"]].join(counts)
    order = order.sort_values(list(order.columns), ascending=False, kind="stable")
    return df.loc[order.index]


def standings(engine: Engine, season: int) -> dict | None:
    """Drivers' and constructors' championships so far, with points after every round."""
    cal = _df(
        engine,
        "select id, round, name, weekend_format from races where season = :s order by round",
        s=season,
    )
    if cal.empty:
        return None
    res = _df(
        engine,
        """select ra.round, r.session, r.driver_id, r.constructor_id, r.position,
                  r.position_text, r.points, coalesce(r.source, 'jolpica') as source
           from results r join races ra on ra.id = r.race_id
           where ra.season = :s order by ra.round, r.session, r.position_order""",
        s=season,
    )
    refs, teams = driver_refs(engine), team_names(engine)
    gp = res[res["session"] == "R"]
    gp_done = set(gp["round"])
    sprint_done = set(res.loc[res["session"] == "S", "round"])
    gps_left = int((~cal["round"].isin(gp_done)).sum())
    sprints_left = int(
        ((cal["weekend_format"] == "sprint") & ~cal["round"].isin(sprint_done)).sum()
    )
    gp_drv, gp_team, sp_drv, sp_team = _max_points(season)
    left_driver = gps_left * gp_drv + sprints_left * sp_drv
    left_team = gps_left * gp_team + sprints_left * sp_team

    rounds = sorted(set(res["round"]))
    names = dict(zip(cal["round"], cal["name"], strict=True))
    ids = dict(zip(cal["round"], cal["id"], strict=True))

    def table(key: str) -> tuple[pd.DataFrame, dict[str, list[float]]]:
        if res.empty:
            return pd.DataFrame(columns=["points", "wins", "podiums", "gap"]), {}
        per_round = res.pivot_table(index=key, columns="round", values="points", aggfunc="sum")
        per_round = per_round.reindex(columns=rounds).fillna(0).cumsum(axis=1)
        df = pd.DataFrame(
            {
                "points": res.groupby(key)["points"].sum(),
                "wins": gp[gp["position"] == 1].groupby(key).size(),
                "podiums": gp[gp["position"] <= 3].groupby(key).size(),
            }
        ).fillna(0)
        df = _ranked(df, key, gp)
        df["gap"] = float(df["points"].iloc[0]) - df["points"]
        progression = {k: [float(v) for v in row] for k, row in per_round.iterrows()}
        return df, progression

    latest_team = res.groupby("driver_id")["constructor_id"].last()
    drv, drv_prog = table("driver_id")
    form = {d: g.tail(5) for d, g in gp.groupby("driver_id")}
    drivers = [
        {
            "position": i + 1,
            "driver": driver_ref(refs, teams, d, latest_team[d]),
            "points": float(r["points"]),
            "wins": int(r["wins"]),
            "podiums": int(r["podiums"]),
            "gap": float(r["gap"]),
            "in_contention": bool(r["gap"] <= left_driver),
            "form": [
                {"round": int(f["round"]), "text": str(f["position_text"])}
                for f in form[d].to_dict("records")
            ]
            if d in form
            else [],
        }
        for i, (d, r) in enumerate(drv.iterrows())
    ]

    team, team_prog = table("constructor_id")
    lineups: dict[str, list[str]] = {}
    for d, t in latest_team.items():
        lineups.setdefault(t, []).append(d)
    constructors = [
        {
            "position": i + 1,
            "team_id": t,
            "team_name": teams.get(t, t),
            "points": float(r["points"]),
            "wins": int(r["wins"]),
            "podiums": int(r["podiums"]),
            "gap": float(r["gap"]),
            "in_contention": bool(r["gap"] <= left_team),
            "drivers": [
                driver_ref(refs, teams, d, t)
                for d in sorted(lineups.get(t, []), key=lambda d: -drv.loc[d, "points"])
            ],
        }
        for i, (t, r) in enumerate(team.iterrows())
    ]

    return {
        "season": season,
        "rounds_total": len(cal),
        "rounds_done": len(gp_done),
        "points_left_driver": left_driver,
        "points_left_team": left_team,
        "provisional": bool((res["source"] != "jolpica").any()),
        "rounds": [{"round": int(r), "race_id": ids[r], "name": names[r]} for r in rounds],
        "drivers": drivers,
        "constructors": constructors,
        "driver_progression": drv_prog,
        "team_progression": team_prog,
    }
