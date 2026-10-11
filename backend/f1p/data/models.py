"""SQLAlchemy schema for the local race database."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Race(Base):
    """One Grand Prix weekend. ``id`` is ``"{season}-{round}"``, e.g. ``"2026-17"``."""

    __tablename__ = "races"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    round: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)
    circuit_id: Mapped[str] = mapped_column(String, index=True)
    circuit_name: Mapped[str] = mapped_column(String)
    locality: Mapped[str | None] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String)
    race_date: Mapped[date] = mapped_column(Date)
    race_start_utc: Mapped[datetime | None] = mapped_column(DateTime)
    quali_start_utc: Mapped[datetime | None] = mapped_column(DateTime)
    sprint_start_utc: Mapped[datetime | None] = mapped_column(DateTime)
    weekend_format: Mapped[str] = mapped_column(String)  # "conventional" | "sprint"


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Jolpica/FastF1 driverId
    code: Mapped[str | None] = mapped_column(String)
    permanent_number: Mapped[int | None] = mapped_column(Integer)
    given_name: Mapped[str] = mapped_column(String)
    family_name: Mapped[str] = mapped_column(String)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String)


class Constructor(Base):
    __tablename__ = "constructors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    nationality: Mapped[str | None] = mapped_column(String)


class Result(Base):
    """Classification of a Grand Prix (``session="R"``) or sprint (``session="S"``)."""

    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("race_id", "session", "driver_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.id"), index=True)
    session: Mapped[str] = mapped_column(String)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    constructor_id: Mapped[str] = mapped_column(ForeignKey("constructors.id"))
    car_number: Mapped[int | None] = mapped_column(Integer)
    grid: Mapped[int | None] = mapped_column(Integer)  # 0 = pit-lane start
    position: Mapped[int | None] = mapped_column(Integer)  # None when not classified
    position_text: Mapped[str] = mapped_column(String)  # "1".."22", "R", "D", "W", ...
    position_order: Mapped[int] = mapped_column(Integer)  # Always set; order of the sheet
    points: Mapped[float] = mapped_column(Float)
    laps: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    time_ms: Mapped[int | None] = mapped_column(Integer)
    classified: Mapped[bool] = mapped_column()
    source: Mapped[str | None] = mapped_column(String)  # "jolpica" (official) | "fastf1"


class QualifyingResult(Base):
    __tablename__ = "qualifying"
    __table_args__ = (UniqueConstraint("race_id", "driver_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    constructor_id: Mapped[str] = mapped_column(ForeignKey("constructors.id"))
    position: Mapped[int] = mapped_column(Integer)
    q1_s: Mapped[float | None] = mapped_column(Float)
    q2_s: Mapped[float | None] = mapped_column(Float)
    q3_s: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String)  # "jolpica" (official) | "fastf1"


class SessionRecord(Base):
    """Ingest status of one FastF1 session, plus its weather summary."""

    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("race_id", "session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.id"), index=True)
    session: Mapped[str] = mapped_column(String)  # FP1 FP2 FP3 SQ S Q R
    start_utc: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String)  # "ok" | "no_data" | "error"
    error: Mapped[str | None] = mapped_column(String)
    n_laps: Mapped[int | None] = mapped_column(Integer)
    laps_path: Mapped[str | None] = mapped_column(String)
    air_temp: Mapped[float | None] = mapped_column(Float)
    track_temp: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    rainfall_frac: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class Prediction(Base):
    """An immutable prediction snapshot for one race and stage. Never updated, only added."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.id"), index=True)
    stage: Mapped[str] = mapped_column(String)  # "pre" | "post"
    created_at: Mapped[datetime] = mapped_column(DateTime)
    cutoff_utc: Mapped[datetime] = mapped_column(DateTime)
    # True only if made before the cutoff (quali start / race start): a genuine forecast.
    made_before_cutoff: Mapped[bool] = mapped_column()
    model_trained_through: Mapped[str] = mapped_column(String)
    temperature: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String)
    # Bad-day settings of the simulator (null on snapshots made before they existed = none).
    incident_rate: Mapped[float | None] = mapped_column(Float)
    incident_drop: Mapped[float | None] = mapped_column(Float)


class PredictionRow(Base):
    __tablename__ = "prediction_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    constructor_id: Mapped[str] = mapped_column(String)
    pred_rank: Mapped[int] = mapped_column(Integer)
    expected_pos: Mapped[float] = mapped_column(Float)
    p_win: Mapped[float] = mapped_column(Float)
    p_podium: Mapped[float] = mapped_column(Float)
    p_points: Mapped[float] = mapped_column(Float)
    position_probs: Mapped[str] = mapped_column(String)  # JSON list, P(P1), P(P2), ...
    score: Mapped[float | None] = mapped_column(Float)  # ranker score fed to the simulator
    p_dnf: Mapped[float | None] = mapped_column(Float)


class PredictionScore(Base):
    """How a snapshot did once the race was run, next to a simple baseline on the same race."""

    __tablename__ = "prediction_scores"

    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), primary_key=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime)
    n_drivers: Mapped[int] = mapped_column(Integer)
    spearman: Mapped[float] = mapped_column(Float)
    pos_mae: Mapped[float] = mapped_column(Float)
    winner_hit: Mapped[float] = mapped_column(Float)
    top3_hit: Mapped[float] = mapped_column(Float)
    top10_hit: Mapped[float] = mapped_column(Float)
    win_logloss: Mapped[float] = mapped_column(Float)
    win_brier: Mapped[float] = mapped_column(Float)
    podium_logloss: Mapped[float] = mapped_column(Float)
    podium_brier: Mapped[float] = mapped_column(Float)
    points_logloss: Mapped[float] = mapped_column(Float)
    points_brier: Mapped[float] = mapped_column(Float)
    pos_logloss: Mapped[float | None] = mapped_column(Float)
    baseline_name: Mapped[str] = mapped_column(String)
    baseline_metrics: Mapped[str] = mapped_column(String)  # JSON, same keys as above


class Player(Base):
    """A 'Beat the model' player. Authenticated by a random token; only its hash is stored."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String)
    nickname_key: Mapped[str] = mapped_column(String, unique=True)  # lower-cased, for uniqueness
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Pick(Base):
    """A player's podium pick for one race. Editable until the race starts."""

    __tablename__ = "picks"
    __table_args__ = (UniqueConstraint("player_id", "race_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    race_id: Mapped[str] = mapped_column(ForeignKey("races.id"), index=True)
    p1: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    p2: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    p3: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
