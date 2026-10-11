"""Shared fixtures: a temporary database holding a small, hand-built championship."""

import numpy as np
import pandas as pd
import pytest

from f1p import config
from f1p.data.db import get_engine, get_session, upsert
from f1p.data.models import Constructor, Driver, QualifyingResult, Race, Result
from tests.test_features import _mini_tables


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A temporary database holding the mini championship from the feature tests."""
    t = _mini_tables(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    engine = get_engine(tmp_path / "test.sqlite")

    def cols(model, frame):
        names = [c.name for c in model.__table__.columns if c.name != "id" or model is Race]
        return frame[[c for c in names if c in frame.columns]].replace({np.nan: None})

    races = t.races.assign(race_date=pd.to_datetime(t.races["race_date"]).dt.date)
    with get_session(engine) as s:
        upsert(s, Race, cols(Race, races).to_dict("records"), ["id"])
        upsert(s, Constructor, [{"id": c, "name": c, "nationality": None}
                                for c in t.results.constructor_id.unique()], ["id"])  # fmt: skip
        drivers = [
            {"id": d, "code": c, "permanent_number": None, "given_name": d, "family_name": d,
             "date_of_birth": None, "nationality": None}
            for d, c in zip(t.drivers.id, t.drivers.code, strict=True)
        ]  # fmt: skip
        upsert(s, Driver, drivers, ["id"])
        results = cols(Result, t.results).to_dict("records")
        upsert(s, Result, results, ["race_id", "session", "driver_id"])
        quali = cols(QualifyingResult, t.qualifying).to_dict("records")
        upsert(s, QualifyingResult, quali, ["race_id", "driver_id"])
        s.commit()
    return engine
