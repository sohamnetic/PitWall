"""Command-line entry point: f1p ingest | train | predict | score | backtest."""

from __future__ import annotations

import logging
from enum import Enum

import typer

app = typer.Typer(help="F1 Grand Prix race predictor pipeline.", no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not verbose:
        logging.getLogger("fastf1").setLevel(logging.WARNING)


class Stage(str, Enum):
    pre = "pre"
    post = "post"


@app.command()
def ingest(
    seasons: str = typer.Option("2014-2026", help="Season or range, e.g. 2024 or 2018-2026."),
    results: bool = typer.Option(True, help="Fetch calendar, results and qualifying (Jolpica)."),
    laps: bool = typer.Option(True, help="Fetch FastF1 lap data (2018+ only)."),
    sessions: str = typer.Option("FP1,FP2,FP3,SQ,S,Q,R", help="FastF1 sessions to fetch."),
    force: bool = typer.Option(False, help="Re-download sessions already stored."),
) -> None:
    """Fetch results and lap data into the local database (incremental)."""
    from f1p import config
    from f1p.data.ingest import ingest_laps, ingest_results, parse_seasons

    config.ensure_dirs()
    season_list = parse_seasons(seasons)
    if results:
        ingest_results(season_list)
    if laps:
        lap_seasons = [s for s in season_list if s >= config.LAPS_FIRST_SEASON]
        codes = tuple(c.strip().upper() for c in sessions.split(",") if c.strip())
        ingest_laps(lap_seasons, codes, force=force)


@app.command()
def status() -> None:
    """Summarise what is in the local database."""
    from sqlalchemy import func, select

    from f1p.data.db import get_session
    from f1p.data.models import QualifyingResult, Race, Result, SessionRecord

    with get_session() as db:
        typer.echo(f"{'season':>6} {'races':>5} {'w/res':>5} {'results':>7} {'quali':>5}  sessions")
        for season in db.scalars(select(Race.season).distinct().order_by(Race.season)):
            race_ids = select(Race.id).where(Race.season == season)
            n_races = db.scalar(select(func.count()).where(Race.season == season))
            n_with = db.scalar(
                select(func.count(func.distinct(Result.race_id))).where(
                    Result.race_id.in_(race_ids), Result.session == "R"
                )
            )
            n_res = db.scalar(select(func.count()).where(Result.race_id.in_(race_ids)))
            n_q = db.scalar(select(func.count()).where(QualifyingResult.race_id.in_(race_ids)))
            by_status = dict(
                db.execute(
                    select(SessionRecord.status, func.count())
                    .where(SessionRecord.race_id.in_(race_ids))
                    .group_by(SessionRecord.status)
                ).all()
            )
            sess = " ".join(f"{k}={v}" for k, v in sorted(by_status.items())) or "-"
            typer.echo(f"{season:>6} {n_races:>5} {n_with:>5} {n_res:>7} {n_q:>5}  {sess}")


@app.command()
def features(stage: Stage = typer.Option(Stage.post)) -> None:
    """Build the point-in-time feature matrix and save it to data/features/<stage>.parquet."""
    from f1p import config
    from f1p.features.build import build_features, feature_columns

    df = build_features(stage.value)
    out = config.DATA_DIR / "features" / f"{stage.value}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    typer.echo(f"{len(df)} rows x {len(feature_columns(stage.value))} features -> {out}")
    missing = df[feature_columns(stage.value)].isna().mean().sort_values(ascending=False)
    typer.echo("Missing share (top 8):")
    typer.echo(missing.head(8).round(3).to_string())


@app.command()
def train(stage: str = typer.Option("both", help="pre, post or both.")) -> None:
    """Train the ranker, DNF model and temperature on every completed race; save to disk."""
    from f1p.features.build import build_features
    from f1p.models.race_model import RaceModel, model_path

    for st in ("pre", "post") if stage == "both" else (stage,):
        df = build_features(st)
        train_rows = df[(df["started"] == 1) & df["finish_order"].notna()]
        last = train_rows.sort_values("race_idx")["race_id"].iloc[-1]
        model = RaceModel(st).fit(train_rows)
        model.save(model_path(st), trained_through=last)
        typer.echo(
            f"{st}: trained on {train_rows['race_id'].nunique()} races through {last}, "
            f"temperature {model.temperature:.3f} -> {model_path(st)}"
        )
        typer.echo("  top features: " + ", ".join(model.ranker.importance().head(6).index))


def _refresh(season: int) -> None:
    from f1p import config
    from f1p.data.ingest import ingest_laps, ingest_results
    from f1p.data.provisional import fill_provisional

    config.ensure_dirs()
    ingest_results([season])
    ingest_laps([season])
    fill_provisional(season)


@app.command()
def auto(refresh: bool = typer.Option(True, help="Fetch the latest data first.")) -> None:
    """Race-weekend autopilot: forecast when new sessions are in, score finished races.

    Safe to run as often as you like (e.g. hourly from Task Scheduler or cron): it only acts
    when something new is available. Each forecast is a new immutable snapshot.
    """
    from sqlalchemy import select

    from f1p.data.db import get_session
    from f1p.data.models import Prediction
    from f1p.features.tables import load_tables
    from f1p.pipeline.live import predict as run_predict
    from f1p.pipeline.live import resolve_race, score_race, utcnow

    now = utcnow()
    if refresh:
        _refresh(now.year)
    t = load_tables()

    try:
        last = resolve_race(t, "last", now)
        scored = score_race(last)
        typer.echo(f"{last}: scored {len(scored)} snapshot(s)" if scored else f"{last}: up to date")
    except ValueError as e:
        typer.echo(f"scoring: {e}")

    try:
        race_id = resolve_race(t, "next", now)
    except ValueError as e:
        typer.echo(f"forecast: {e}")
        return
    with get_session() as db:
        have = set(db.scalars(select(Prediction.stage).where(Prediction.race_id == race_id)))
    practice_done = (
        (t.sessions["race_id"] == race_id)
        & (t.sessions["status"] == "ok")
        & t.sessions["session"].isin(["FP1", "FP2", "FP3", "SQ"])
    ).any()
    quali_done = (t.qualifying["race_id"] == race_id).any()

    if quali_done and "post" not in have:
        _show_snapshot(run_predict(race_id, "post", now))
    elif practice_done and not quali_done and "pre" not in have:
        _show_snapshot(run_predict(race_id, "pre", now))
    else:
        stage = "post" if quali_done else "pre" if practice_done else "none (no session run yet)"
        typer.echo(f"{race_id}: nothing new to forecast (stage {stage}; have {sorted(have)})")


@app.command()
def backfill(
    season: int = typer.Option(..., help="Season whose finished races get backfilled."),
) -> None:
    """Predict every finished race of a season that has no prediction yet, then score them.

    Each backfill is built only from data available at its cutoff, with a model trained only
    on earlier races, and is labelled 'backfill' (never counted as a live forecast).
    """
    from sqlalchemy import select

    from f1p.data.db import get_session
    from f1p.data.models import Prediction
    from f1p.features.tables import load_tables
    from f1p.pipeline.live import predict as run_predict
    from f1p.pipeline.live import score_race, utcnow

    t = load_tables()
    finished = set(t.results.loc[t.results["session"] == "R", "race_id"])
    races = t.races[(t.races["season"] == season) & t.races["id"].isin(finished)]
    with get_session() as db:
        have = set(db.execute(select(Prediction.race_id, Prediction.stage)).all())
    made = 0
    for race_id in races.sort_values("race_idx")["id"]:
        for stage in ("pre", "post"):
            if (race_id, stage) in have:
                continue
            run_predict(race_id, stage, utcnow())
            made += 1
        scored = score_race(race_id)
        typer.echo(f"{race_id}: {len(scored)} snapshot(s) scored")
    typer.echo(f"Backfilled {made} prediction(s) for {season}.")


def _show_snapshot(prediction_id: int) -> None:
    import pandas as pd
    from sqlalchemy import text

    from f1p.data.db import get_engine
    from f1p.pipeline.live import load_snapshot

    snap = load_snapshot(prediction_id)
    p = snap.prediction
    engine = get_engine()
    race = pd.read_sql(
        text("select name from races where id = :r"), engine, params={"r": p.race_id}
    )["name"].iloc[0]
    names = pd.read_sql("select id, given_name || ' ' || family_name as name from drivers", engine)
    teams = pd.read_sql("select id, name as team from constructors", engine)
    rows = snap.rows.merge(names, left_on="driver_id", right_on="id").merge(
        teams, left_on="constructor_id", right_on="id"
    )
    timing = "before" if p.made_before_cutoff else "AFTER (backfill, as-of data)"
    typer.echo(f"\n{race} ({p.race_id}) - {p.stage}-qualifying prediction #{p.id}")
    typer.echo(
        f"made {p.created_at:%Y-%m-%d %H:%M} UTC, {timing} the cutoff "
        f"{p.cutoff_utc:%Y-%m-%d %H:%M} UTC; model trained through {p.model_trained_through}\n"
    )
    header = f"{'#':>3}  {'Driver':<22}{'Team':<22}"
    typer.echo(header + f"{'Win':>6}{'Podium':>8}{'Points':>8}{'Exp':>6}")
    for r in rows.sort_values("pred_rank").itertuples():
        typer.echo(
            f"{r.pred_rank:>3}  {r.name:<22}{r.team[:21]:<22}{r.p_win:>6.0%}"
            f"{r.p_podium:>8.0%}{r.p_points:>8.0%}{r.expected_pos:>6.1f}"
        )


@app.command()
def predict(
    race: str = typer.Option("next", help="'next' or a race id such as 2026-19."),
    stage: str = typer.Option("auto", help="pre, post, or auto (post once quali is published)."),
    refresh: bool = typer.Option(True, help="Fetch the latest results and laps first."),
) -> None:
    """Predict a race and save an immutable prediction snapshot."""
    from f1p.features.tables import load_tables
    from f1p.pipeline.live import auto_stage, resolve_race, utcnow
    from f1p.pipeline.live import predict as run_predict

    now = utcnow()
    if refresh:
        _refresh(now.year)
    t = load_tables()
    race_id = resolve_race(t, race, now)
    st = auto_stage(t, race_id) if stage == "auto" else stage
    _show_snapshot(run_predict(race_id, st, now))


@app.command()
def score(
    race: str = typer.Option("last", help="'last' or a race id such as 2026-18."),
    refresh: bool = typer.Option(True, help="Fetch the latest results first."),
) -> None:
    """Score saved predictions for a completed race against the actual result."""
    import json

    from f1p.data.ingest import ingest_results
    from f1p.features.tables import load_tables
    from f1p.pipeline.live import resolve_race, score_race, track_record, utcnow

    now = utcnow()
    if refresh:
        ingest_results([now.year])
    race_id = resolve_race(load_tables(), race, now)
    ids = score_race(race_id)
    if not ids:
        typer.echo(f"No unscored predictions for {race_id}.")
        return
    rec = track_record().set_index("id").loc[ids]
    import pandas as pd

    from f1p.data.db import get_engine

    scores = pd.read_sql("select * from prediction_scores", get_engine()).set_index("prediction_id")
    for pid, r in rec.iterrows():
        s = scores.loc[pid]
        b = json.loads(s["baseline_metrics"])
        typer.echo(f"\n{r['race']} - {r['stage']}-qualifying prediction #{pid}")
        typer.echo(f"{'':<16}{'model':>10}{s['baseline_name']:>14}")
        for key, label in (
            ("spearman", "order corr."),
            ("winner_hit", "winner right"),
            ("top3_hit", "top-3 overlap"),
            ("top10_hit", "top-10 overlap"),
            ("win_logloss", "win log-loss"),
            ("podium_brier", "podium Brier"),
        ):
            typer.echo(f"{label:<16}{s[key]:>10.3f}{b[key]:>14.3f}")


@app.command()
def record() -> None:
    """Track record of every saved prediction (scored ones vs their baseline)."""
    import pandas as pd

    from f1p.pipeline.live import track_record

    pd.set_option("display.width", 200)
    df = track_record()
    if df.empty:
        typer.echo("No predictions saved yet.")
        return
    df["when"] = df["made_before_cutoff"].astype(bool).map({True: "live", False: "backfill"})
    cols = ["id", "race", "stage", "when", "spearman", "base_spearman", "winner_hit",
            "win_logloss", "base_win_logloss", "baseline_name"]  # fmt: skip
    typer.echo(df[cols].round(3).to_string(index=False))
    scored = df.dropna(subset=["spearman"])
    if not scored.empty:
        typer.echo(
            f"\n{len(scored)} scored: model order corr. {scored.spearman.mean():.3f} vs "
            f"baseline {scored.base_spearman.mean():.3f}; win log-loss "
            f"{scored.win_logloss.mean():.3f} vs {scored.base_win_logloss.mean():.3f}"
        )


@app.command()
def backtest(
    seasons: str = typer.Option("2022-2026", help="Seasons to test on (trained on all earlier)."),
    stage: str = typer.Option("both", help="pre, post or both."),
) -> None:
    """Walk-forward backtest: predict each race using only races before it."""
    import pandas as pd

    from f1p import config
    from f1p.data.ingest import parse_seasons
    from f1p.eval.backtest import walk_forward
    from f1p.features.build import build_features
    from f1p.models.baselines import baselines_for
    from f1p.models.race_model import RaceModel

    pd.set_option("display.width", 200)
    test_seasons = parse_seasons(seasons)
    out_dir = config.DATA_DIR / "backtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    show = ["races", "spearman", "pos_mae", "winner_hit", "top3_hit", "top10_hit",
            "win_logloss", "podium_brier", "points_brier"]  # fmt: skip

    for st in ("pre", "post") if stage == "both" else (stage,):
        predictors = [RaceModel(st), *baselines_for(st)]
        result = walk_forward(build_features(st), predictors, test_seasons)
        result.races.to_parquet(out_dir / f"{st}_races.parquet", index=False)
        result.drivers.to_parquet(out_dir / f"{st}_drivers.parquet", index=False)
        summary = result.summary()[show].sort_values("spearman", ascending=False)
        typer.echo(f"\n=== {st.upper()}-QUALIFYING, seasons {seasons} ===")
        typer.echo(summary.round(3).to_string())
        by_season = result.summary(("model", "season"))["spearman"].unstack().round(3)
        typer.echo("\nSpearman by season:")
        typer.echo(by_season.loc[summary.index].to_string())


if __name__ == "__main__":
    app()
