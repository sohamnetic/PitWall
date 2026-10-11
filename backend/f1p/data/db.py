"""Database engine, sessions and upsert helper."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker

from f1p import config
from f1p.data.models import Base


@lru_cache
def get_engine(db_path: Path | None = None) -> Engine:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine: Engine) -> None:
    """Minimal migration: add nullable columns that exist in the models but not the database."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing and col.nullable:
                    col_type = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))


def get_session(engine: Engine | None = None) -> Session:
    return sessionmaker(bind=engine or get_engine())()


def upsert(session: Session, model: type[Base], rows: Iterable[dict], conflict_cols: list[str]):
    """Insert rows, updating every non-key column when ``conflict_cols`` already exist."""
    rows = list(rows)
    if not rows:
        return
    # SQLite caps bound parameters per statement, so insert in chunks.
    chunk = max(1, 900 // len(rows[0]))
    for i in range(0, len(rows), chunk):
        stmt = insert(model).values(rows[i : i + chunk])
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in model.__table__.columns
            if c.name not in conflict_cols and not c.primary_key
        }
        session.execute(stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update_cols))
