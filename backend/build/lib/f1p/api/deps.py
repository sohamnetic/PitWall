from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine

from f1p.data.db import get_engine


def get_db() -> Engine:
    """Database engine dependency (overridden in tests)."""
    return get_engine()


def get_now() -> datetime:
    """Current UTC time, naive like the database (overridden in tests)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
