from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine

from f1p.api import queries, simulation
from f1p.api.deps import get_db
from f1p.api.schemas import RaceField, SimulateIn, SimulateOut
from f1p.models.questions import Question
from f1p.models.scenario import Scenario, ScenarioError

router = APIRouter(tags=["ask the model"])


@router.get("/races/{race_id}/field", response_model=RaceField)
def race_field(race_id: str, db: Engine = Depends(get_db)):
    """Drivers in the race in current (or predicted) starting order: the what-if editor's start."""
    try:
        f = simulation.race_field(db, race_id)
    except KeyError:
        raise HTTPException(404, f"Unknown race {race_id}") from None
    refs, teams = queries.driver_refs(db), queries.team_names(db)
    drivers = [queries.driver_ref(refs, teams, d, f["teams"].get(d)) for d in f["order"]]
    team_ids = sorted({t for t in f["teams"].values() if t}, key=lambda t: teams.get(t, t))
    return {
        "race_id": race_id,
        "completed": f["completed"],
        "grid_source": f["grid_source"],
        "drivers": drivers,
        "teams": [{"id": t, "name": teams.get(t, t)} for t in team_ids],
    }


@router.post("/races/{race_id}/simulate", response_model=SimulateOut)
def simulate(race_id: str, body: SimulateIn, db: Engine = Depends(get_db)):
    """Answer custom questions, optionally under a what-if scenario (upcoming races only).

    Without a scenario, questions are answered from the race's saved prediction, so the
    numbers match what the prediction pages show. With a scenario, the post-qualifying model
    re-runs on the modified grid.
    """
    scenario = Scenario(**body.scenario.model_dump()) if body.scenario else None
    questions = [Question(**q.model_dump()) for q in body.questions]
    try:
        out = simulation.run(db, race_id, scenario, questions, stage=body.stage)
    except KeyError:
        raise HTTPException(404, f"Unknown race {race_id}") from None
    except simulation.SimulationUnavailable as e:
        raise HTTPException(409, str(e)) from None
    except ScenarioError as e:
        raise HTTPException(422, str(e)) from None

    refs, teams = queries.driver_refs(db), queries.team_names(db)
    frame = out.pop("frame").sort_values("pred_rank")
    out["rows"] = [
        {
            "driver": queries.driver_ref(refs, teams, r["driver_id"], r["constructor_id"]),
            **{k: r[k] for k in ("pred_rank", "expected_pos", "p_win", "p_podium", "p_points")},
            "position_probs": json.loads(r["position_probs"]),
            "actual_position": None,
        }
        for r in frame.to_dict("records")
    ]
    out["answers"] = [{**a, "question": vars(a["question"])} for a in out["answers"]]
    return out
