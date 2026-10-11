"""'Beat the model' endpoints: players, podium picks, race summaries and the leaderboard."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError

from f1p import game
from f1p.api import queries, simulation
from f1p.api.deps import get_db, get_now
from f1p.api.schemas import (
    LeaderboardEntry,
    PickHistoryEntry,
    PickIn,
    PickOut,
    PicksSummary,
    PlayerCreate,
    PlayerCreated,
    PlayerOut,
)
from f1p.data.db import get_session
from f1p.data.models import Pick, Player

router = APIRouter(tags=["beat the model"])


def current_player(
    x_player_token: str | None = Header(None), db: Engine = Depends(get_db)
) -> Player:
    if not x_player_token:
        raise HTTPException(401, "Missing X-Player-Token header")
    with get_session(db) as s:
        token_hash = game.hash_token(x_player_token)
        player = s.scalar(select(Player).where(Player.token_hash == token_hash))
        if player is None:
            raise HTTPException(401, "Unknown player token")
        s.expunge(player)
        return player


def _race(db: Engine, race_id: str) -> dict:
    races = queries.race_summaries(db, race_id=race_id)
    if not races:
        raise HTTPException(404, f"Unknown race {race_id}")
    return races[0]


def _lock_time(race: dict) -> datetime:
    return pd.Timestamp(race["race_start_utc"] or race["race_date"]).to_pydatetime()


def _podium(db: Engine, race_id: str) -> list[str] | None:
    """Official top three, once published."""
    df = pd.read_sql(
        text(
            "select driver_id from results where race_id = :r and session = 'R' "
            "and coalesce(source, 'jolpica') = 'jolpica' and position_order <= 3 "
            "order by position_order"
        ),
        db,
        params={"r": race_id},
    )
    return list(df["driver_id"]) if len(df) == 3 else None


def _model_pick(db: Engine, race_id: str) -> list[str] | None:
    """Top three of the latest forecast made before the race (post-quali preferred)."""
    df = pd.read_sql(
        text(
            """select pr.driver_id from prediction_rows pr
               where pr.prediction_id = (
                 select id from predictions where race_id = :r and made_before_cutoff = 1
                 order by case stage when 'post' then 0 else 1 end, id desc limit 1)
               and pr.pred_rank <= 3 order by pr.pred_rank"""
        ),
        db,
        params={"r": race_id},
    )
    return list(df["driver_id"]) if len(df) == 3 else None


@router.post("/players", response_model=PlayerCreated, status_code=201)
def create_player(body: PlayerCreate, db: Engine = Depends(get_db), now=Depends(get_now)):
    nickname = " ".join(body.nickname.split())
    if not game.valid_nickname(nickname):
        raise HTTPException(
            422, "Nickname: 3-20 letters, numbers, spaces, '.', '_' or '-' (not 'The Model')"
        )
    token, token_hash = game.new_token()
    with get_session(db) as s:
        player = Player(
            nickname=nickname, nickname_key=nickname.lower(), token_hash=token_hash, created_at=now
        )
        s.add(player)
        try:
            s.commit()
        except IntegrityError:
            raise HTTPException(409, "That nickname is taken") from None
        return {"id": player.id, "nickname": player.nickname, "token": token}


@router.get("/players/me", response_model=PlayerOut)
def me(player: Player = Depends(current_player)):
    return {"id": player.id, "nickname": player.nickname}


def _pick_out(db: Engine, pick: Pick, race: dict, now: datetime) -> dict:
    refs, teams = queries.driver_refs(db), queries.team_names(db)
    podium = _podium(db, race["id"])
    ids = [pick.p1, pick.p2, pick.p3]
    return {
        "race_id": race["id"],
        "podium": [queries.driver_ref(refs, teams, d) for d in ids],
        "updated_at": pick.updated_at,
        "locked": now >= _lock_time(race),
        "points": game.score_pick(ids, podium) if podium else None,
    }


@router.get("/players/me/picks", response_model=list[PickHistoryEntry])
def my_picks(
    player: Player = Depends(current_player), db: Engine = Depends(get_db), now=Depends(get_now)
):
    """Every pick this player has made, newest race first, with points once scored."""
    with get_session(db) as s:
        picks = list(s.scalars(select(Pick).where(Pick.player_id == player.id)))
        s.expunge_all()
    refs, teams = queries.driver_refs(db), queries.team_names(db)
    out = []
    for pick in picks:
        race = _race(db, pick.race_id)
        podium = _podium(db, pick.race_id)
        out.append(
            {
                **_pick_out(db, pick, race, now),
                "race_name": race["name"],
                "actual_podium": [queries.driver_ref(refs, teams, d) for d in podium]
                if podium
                else None,
            }
        )
    return sorted(out, key=lambda e: e["race_id"], reverse=True)


@router.get("/races/{race_id}/picks/me", response_model=PickOut)
def my_pick(
    race_id: str,
    player: Player = Depends(current_player),
    db: Engine = Depends(get_db),
    now=Depends(get_now),
):
    race = _race(db, race_id)
    with get_session(db) as s:
        pick = s.scalar(select(Pick).where(Pick.player_id == player.id, Pick.race_id == race_id))
        if pick is None:
            raise HTTPException(404, "No pick for this race yet")
        return _pick_out(db, pick, race, now)


@router.put("/races/{race_id}/picks/me", response_model=PickOut)
def save_pick(
    race_id: str,
    body: PickIn,
    player: Player = Depends(current_player),
    db: Engine = Depends(get_db),
    now=Depends(get_now),
):
    race = _race(db, race_id)
    if now >= _lock_time(race):
        raise HTTPException(409, "Picks are locked: the race has started")
    ids = [body.p1, body.p2, body.p3]
    if len(set(ids)) != 3:
        raise HTTPException(422, "Pick three different drivers")
    entrants = set(simulation.race_field(db, race_id)["order"])
    unknown = set(ids) - entrants
    if unknown:
        raise HTTPException(422, f"Not in this race: {', '.join(sorted(unknown))}")
    with get_session(db) as s:
        pick = s.scalar(select(Pick).where(Pick.player_id == player.id, Pick.race_id == race_id))
        if pick is None:
            pick = Pick(player_id=player.id, race_id=race_id, updated_at=now)
            s.add(pick)
        pick.p1, pick.p2, pick.p3 = ids
        pick.updated_at = now
        s.commit()
        s.refresh(pick)
        return _pick_out(db, pick, race, now)


@router.get("/races/{race_id}/picks/summary", response_model=PicksSummary)
def picks_summary(race_id: str, db: Engine = Depends(get_db), now=Depends(get_now)):
    """What the crowd picked, next to the model's pick (and, after the race, the scores)."""
    race = _race(db, race_id)
    lock = _lock_time(race)
    locked = now >= lock
    picks = pd.read_sql(
        text("select p1, p2, p3 from picks where race_id = :r"), db, params={"r": race_id}
    )
    refs, teams = queries.driver_refs(db), queries.team_names(db)

    def ref(d: str) -> dict:
        return queries.driver_ref(refs, teams, d)

    podium = _podium(db, race_id)
    model = _model_pick(db, race_id)
    crowd: list[str] = []
    for col in ("p1", "p2", "p3"):
        choice = next((d for d in picks[col].value_counts().index if d not in crowd), None)
        if choice:
            crowd.append(choice)
    crowd_pts = None
    if podium and len(picks):
        pts = [game.score_pick([r.p1, r.p2, r.p3], podium) for r in picks.itertuples()]
        crowd_pts = sum(pts) / len(pts)
    return {
        "race_id": race_id,
        "locked": locked,
        "lock_at_utc": lock,
        "n_players": len(picks),
        "winner_picks": [
            {"driver": ref(d), "count": int(c)} for d, c in picks["p1"].value_counts().items()
        ],
        "crowd_podium": [ref(d) for d in crowd],
        # The model's pick is revealed once picks lock, so nobody simply copies it.
        "model_podium": [ref(d) for d in model] if model and locked else None,
        "actual_podium": [ref(d) for d in podium] if podium else None,
        "crowd_avg_points": crowd_pts,
        "model_points": game.score_pick(model, podium) if model and podium else None,
    }


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    season: int | None = Query(None), db: Engine = Depends(get_db), now=Depends(get_now)
):
    season = season or now.year
    races = [r for r in queries.race_summaries(db, season=season) if r["status"] == "completed"]
    picks = pd.read_sql(
        text(
            "select pl.nickname, pk.race_id, pk.p1, pk.p2, pk.p3 from picks pk "
            "join players pl on pl.id = pk.player_id"
        ),
        db,
    )
    totals: dict[tuple[str, bool], list[int]] = {}
    for race in races:
        podium = _podium(db, race["id"])
        if not podium:
            continue
        entries = [
            ((r.nickname, False), [r.p1, r.p2, r.p3])
            for r in picks[picks["race_id"] == race["id"]].itertuples()
        ]
        model = _model_pick(db, race["id"])
        if model:
            entries.append(((game.MODEL_NAME, True), model))
        for key, pick in entries:
            t = totals.setdefault(key, [0, 0, 0])
            t[0] += game.score_pick(pick, podium)
            t[1] += 1
            t[2] += sum(a == b for a, b in zip(pick, podium, strict=True))
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0][0].lower()))
    return [
        {"rank": i + 1, "name": name, "is_model": is_model, "points": p, "races": n, "exact": e}
        for i, ((name, is_model), (p, n, e)) in enumerate(ranked)
    ]
