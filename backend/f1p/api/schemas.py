"""Response models: the API's public contract (also documented at /docs)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["pre", "post"]


class DriverRef(BaseModel):
    id: str
    code: str | None
    name: str
    number: int | None = None
    team_id: str | None = None
    team_name: str | None = None


class Favourite(BaseModel):
    driver: DriverRef
    p_win: float
    stage: Stage
    live: bool = Field(description="Made before the cutoff (a genuine forecast), not a backfill.")


class RaceSummary(BaseModel):
    id: str
    season: int
    round: int
    name: str
    circuit_id: str
    circuit_name: str
    locality: str | None
    country: str | None
    race_date: date
    race_start_utc: datetime | None
    quali_start_utc: datetime | None
    weekend_format: str
    status: Literal["upcoming", "completed"]
    result_source: Literal["official", "none"]
    qualifying_source: Literal["official", "provisional", "none"]
    latest_predictions: dict[str, int | None] = Field(
        description="Latest snapshot id per stage ('pre', 'post'), or null."
    )
    winner: DriverRef | None = None
    favourite: Favourite | None = Field(
        None, description="Model's top pick in the latest snapshot (post-quali preferred)."
    )


class Metrics(BaseModel):
    spearman: float
    pos_mae: float
    winner_hit: float
    top3_hit: float
    top10_hit: float
    win_logloss: float
    win_brier: float
    podium_logloss: float
    podium_brier: float
    points_logloss: float
    points_brier: float


class Score(BaseModel):
    scored_at: datetime
    n_drivers: int
    model: Metrics
    baseline_name: str
    baseline: Metrics


class PredictionRow(BaseModel):
    driver: DriverRef
    pred_rank: int
    expected_pos: float
    p_win: float
    p_podium: float
    p_points: float
    position_probs: list[float] = Field(description="P(P1), P(P2), ... for this driver.")
    actual_position: int | None = Field(None, description="Finishing order, once the race is run.")


class SnapshotMeta(BaseModel):
    id: int
    race_id: str
    stage: Stage
    created_at: datetime
    cutoff_utc: datetime
    made_before_cutoff: bool
    model_trained_through: str
    temperature: float
    model_version: str
    scored: bool


class Snapshot(SnapshotMeta):
    rows: list[PredictionRow]
    score: Score | None


class ResultRow(BaseModel):
    driver: DriverRef
    grid: int | None
    position: int | None
    position_text: str
    position_order: int
    points: float
    laps: int | None
    status: str
    source: str | None


class QualifyingRow(BaseModel):
    driver: DriverRef
    position: int
    q1_s: float | None
    q2_s: float | None
    q3_s: float | None
    source: str | None


class RaceDetail(BaseModel):
    race: RaceSummary
    snapshots: list[SnapshotMeta]
    results: list[ResultRow]
    sprint: list[ResultRow]
    qualifying: list[QualifyingRow]


class BacktestModelSummary(BaseModel):
    model: str
    races: int
    metrics: Metrics


class SeasonPoint(BaseModel):
    model: str
    season: int
    spearman: float
    win_logloss: float


class CalibrationBin(BaseModel):
    predicted: float
    observed: float
    n: int


class VersusCount(BaseModel):
    model: float
    baseline: float


class HeadToHead(BaseModel):
    model: int = Field(description="Races where the model's order was closer to the result.")
    baseline: int
    tie: int


class PlainSeason(BaseModel):
    season: int
    races: int
    h2h_model: int
    h2h_baseline: int
    h2h_tie: int
    model_winners: int
    baseline_winners: int
    model_order: float
    baseline_order: float


class HonestyBand(BaseModel):
    low: float
    high: float
    said: float = Field(description="Average probability the model gave in this band.")
    happened: float = Field(description="How often those events actually happened.")
    n: int


class PlainSummary(BaseModel):
    """The backtest against the obvious guess (grid order / championship order), in counts."""

    baseline: str
    races: int
    head_to_head: HeadToHead
    winners: VersusCount
    podium_drivers: VersusCount = Field(description="Podium finishers named in the top 3, of 3.")
    avg_miss: VersusCount = Field(description="Average places between predicted and actual.")
    seasons: list[PlainSeason]
    honesty: list[HonestyBand] = Field(description="Win, podium and points chances, pooled.")


class StageBacktest(BaseModel):
    summary: list[BacktestModelSummary]
    by_season: list[SeasonPoint]
    calibration: dict[str, list[CalibrationBin]] = Field(
        description="Model's reliability tables for 'win', 'podium' and 'points'."
    )
    plain: PlainSummary | None = None


class TrackRecordEntry(BaseModel):
    snapshot_id: int
    race_id: str
    race_name: str
    stage: Stage
    created_at: datetime
    live: bool
    spearman: float | None
    winner_hit: float | None
    win_logloss: float | None
    baseline_name: str | None
    baseline_spearman: float | None
    baseline_win_logloss: float | None
    pick: DriverRef | None = Field(None, description="The model's favourite.")
    pick_p_win: float | None = None
    winner: DriverRef | None = Field(None, description="Official winner, once published.")


class Performance(BaseModel):
    backtest: dict[str, StageBacktest]
    track_record: list[TrackRecordEntry]


class DriverResult(BaseModel):
    race_id: str
    race_name: str
    team_id: str
    grid: int | None
    quali_position: int | None
    position: int | None
    position_text: str
    points: float


class DriverPrediction(BaseModel):
    snapshot_id: int
    race_id: str
    stage: Stage
    pred_rank: int
    p_win: float
    p_podium: float
    actual_position: int | None


class DriverDetail(BaseModel):
    driver: DriverRef
    nationality: str | None
    season: int
    season_points: float
    recent_results: list[DriverResult]
    predictions: list[DriverPrediction]


# ----------------------------------------------------------------- ask the model / what-if

QuestionKind = Literal[
    "top_k", "position", "ahead", "team_top_k", "team_wins", "podium_exact", "dnf"
]


class QuestionIn(BaseModel):
    kind: QuestionKind
    driver: str | None = None
    other: str | None = None
    team: str | None = None
    k: int | None = Field(None, ge=1, le=30)
    drivers: list[str] = Field(default_factory=list, max_length=3)


class ScenarioIn(BaseModel):
    grid: list[str] | None = Field(None, max_length=30, description="Starting order, P1 first.")
    pit_lane: list[str] = Field(default_factory=list, max_length=30)
    out: list[str] = Field(default_factory=list, max_length=30)
    retire: list[str] = Field(default_factory=list, max_length=30)
    chaos: float = Field(1.0, ge=0.5, le=3.0, description="Multiplies the race's randomness.")


class SimulateIn(BaseModel):
    stage: Stage | None = Field(None, description="Which saved prediction to ask (default latest).")
    scenario: ScenarioIn | None = None
    questions: list[QuestionIn] = Field(default_factory=list, max_length=20)


class Answer(BaseModel):
    question: QuestionIn
    probability: float | None
    happened: bool | None = Field(None, description="Whether it came true (completed races).")
    error: str | None = None


class SimulateOut(BaseModel):
    race_id: str
    source: Literal["snapshot", "scenario"]
    snapshot_id: int | None
    stage: Stage
    n_sims: int
    temperature: float
    grid: list[str] | None
    rows: list[PredictionRow]
    answers: list[Answer]


class RaceField(BaseModel):
    race_id: str
    completed: bool
    grid_source: Literal["qualifying", "predicted"]
    drivers: list[DriverRef] = Field(description="In current (or predicted) starting order.")
    teams: list[dict[str, str]]


# ------------------------------------------------------------------------ beat the model


class PlayerCreate(BaseModel):
    nickname: str = Field(min_length=3, max_length=20)


class PlayerOut(BaseModel):
    id: int
    nickname: str


class PlayerCreated(PlayerOut):
    token: str = Field(description="Keep this secret: it is the only way to edit your picks.")


class PickIn(BaseModel):
    p1: str
    p2: str
    p3: str


class PickOut(BaseModel):
    race_id: str
    podium: list[DriverRef]
    updated_at: datetime
    locked: bool
    points: int | None = None


class PickHistoryEntry(PickOut):
    race_name: str
    actual_podium: list[DriverRef] | None


class PickCount(BaseModel):
    driver: DriverRef
    count: int


class PicksSummary(BaseModel):
    race_id: str
    locked: bool
    lock_at_utc: datetime | None
    n_players: int
    winner_picks: list[PickCount]
    crowd_podium: list[DriverRef] = Field(description="Most-picked driver for each position.")
    model_podium: list[DriverRef] | None
    actual_podium: list[DriverRef] | None
    crowd_avg_points: float | None
    model_points: int | None


class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    is_model: bool
    points: int
    races: int
    exact: int = Field(description="Podium positions called exactly.")


class FormResult(BaseModel):
    round: int
    text: str = Field(description="Finishing position, or R / D / W ... when not classified.")


class DriverStanding(BaseModel):
    position: int
    driver: DriverRef
    points: float
    wins: int
    podiums: int
    gap: float = Field(description="Points behind the leader.")
    in_contention: bool = Field(description="Can still mathematically catch the leader.")
    form: list[FormResult] = Field(description="Last five Grands Prix, oldest first.")


class ConstructorStanding(BaseModel):
    position: int
    team_id: str
    team_name: str
    points: float
    wins: int
    podiums: int
    gap: float
    in_contention: bool
    drivers: list[DriverRef]


class StandingsRound(BaseModel):
    round: int
    race_id: str
    name: str


class Standings(BaseModel):
    season: int
    rounds_total: int
    rounds_done: int = Field(description="Grands Prix run so far.")
    points_left_driver: int = Field(description="Most points one driver can still score.")
    points_left_team: int
    provisional: bool = Field(description="Includes results not yet officially published.")
    rounds: list[StandingsRound] = Field(description="Rounds with any points scored so far.")
    drivers: list[DriverStanding]
    constructors: list[ConstructorStanding]
    driver_progression: dict[str, list[float]] = Field(
        description="Points total after each of `rounds`, per driver id."
    )
    team_progression: dict[str, list[float]]
