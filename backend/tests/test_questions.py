"""Question answering on simulated races, what-if scenarios, and game scoring."""

import numpy as np
import pandas as pd
import pytest

from f1p import game
from f1p.models import questions as qs
from f1p.models.scenario import Scenario, ScenarioError, apply

DRIVERS = ["a", "b", "c", "d"]
TEAMS = {"a": "red", "b": "red", "c": "blue", "d": "blue"}


def _field():
    # Three simulated races (0-based positions per driver).
    finish = np.array(
        [
            [0, 1, 2, 3],  # a b c d
            [1, 0, 3, 2],  # b a d c
            [2, 3, 0, 1],  # c d a b
        ]
    )
    retired = np.array([[False, False, False, True], [False] * 4, [False, True, False, False]])
    return qs.Field(DRIVERS, TEAMS, finish, retired)


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        (qs.Question("top_k", driver="a", k=1), 1 / 3),
        (qs.Question("top_k", driver="a", k=2), 2 / 3),
        (qs.Question("position", driver="d", k=4), 1 / 3),
        (qs.Question("ahead", driver="a", other="b"), 2 / 3),
        (qs.Question("ahead", driver="b", other="a"), 1 / 3),
        (qs.Question("team_top_k", team="red", k=2), 2 / 3),  # one-two
        (qs.Question("team_wins", team="blue"), 1 / 3),
        (qs.Question("podium_exact", drivers=["a", "b", "c"]), 1 / 3),
        (qs.Question("dnf", driver="d"), 1 / 3),
    ],
)
def test_answers(q, expected):
    assert qs.answer(q, _field()) == pytest.approx(expected)


@pytest.mark.parametrize(
    "q",
    [
        qs.Question("top_k", driver="zz", k=1),
        qs.Question("top_k", driver="a", k=9),
        qs.Question("ahead", driver="a", other="a"),
        qs.Question("team_top_k", team="green", k=2),
        qs.Question("podium_exact", drivers=["a", "a", "b"]),
    ],
)
def test_invalid_questions_raise(q):
    with pytest.raises(qs.QuestionError):
        qs.answer(q, _field())


def test_actual_field_checks_what_happened():
    f = qs.actual_field(DRIVERS, TEAMS, {"a": 2, "b": 1, "c": 3, "d": 4}, dnfs={"d"})
    assert qs.outcomes(qs.Question("ahead", driver="b", other="a"), f)[0]
    assert qs.outcomes(qs.Question("dnf", driver="d"), f)[0]
    assert not qs.outcomes(qs.Question("top_k", driver="c", k=2), f)[0]


def _rows(with_quali=True):
    rows = pd.DataFrame(
        {
            "driver_id": DRIVERS,
            "constructor_id": [TEAMS[d] for d in DRIVERS],
            "grid_pct": [0, 1 / 3, 2 / 3, 1] if with_quali else [np.nan] * 4,
            "quali_pos_pct": [0, 1 / 3, 2 / 3, 1] if with_quali else [np.nan] * 4,
            "quali_gap_pct": [0, 0.1, 0.2, 0.3] if with_quali else [np.nan] * 4,
            "pitlane_start": [0.0] * 4,
            "circuit_grid_rho": [0.8] * 4,
        }
    )
    return rows


GAPS = pd.Series({1: 0.0, 2: 0.15, 3: 0.3, 4: 0.5})


def test_pit_lane_start_goes_to_back_and_keeps_quali_pace():
    out = apply(_rows(), Scenario(pit_lane=["a"]), GAPS).set_index("driver_id")
    assert out.loc["a", "grid_pct"] == 1 and out.loc["a", "pitlane_start"] == 1
    assert out.loc["b", "grid_pct"] == 0  # everyone else closes up
    assert out.loc["a", "quali_gap_pct"] == 0  # real qualifying pace is kept
    assert out.loc["a", "grid_x_rho"] == pytest.approx(0.8)


def test_hypothetical_grid_before_qualifying_sets_quali_features():
    out = apply(_rows(with_quali=False), Scenario(grid=["d", "c", "b", "a"]), GAPS)
    out = out.set_index("driver_id")
    assert out.loc["d", "grid_pct"] == 0 and out.loc["d", "quali_pos_pct"] == 0
    assert out.loc["a", "quali_gap_pct"] == 0.5  # typical gap for 4th place


def test_scenario_out_removes_driver_and_validates():
    out = apply(_rows(), Scenario(out=["b"]), GAPS)
    assert list(out["driver_id"]) == ["a", "c", "d"]
    assert out.set_index("driver_id").loc["c", "grid_pct"] == 0.5
    with pytest.raises(ScenarioError):
        apply(_rows(), Scenario(grid=["a", "b", "c"]), GAPS)  # missing driver
    with pytest.raises(ScenarioError):
        apply(_rows(), Scenario(retire=["zz"]), GAPS)
    with pytest.raises(ScenarioError):
        apply(_rows(with_quali=False), Scenario(), GAPS)  # no grid to start from


@pytest.mark.parametrize(
    ("pick", "podium", "points"),
    [
        (["a", "b", "c"], ["a", "b", "c"], 40),  # perfect: 30 + 10 bonus
        (["b", "a", "c"], ["a", "b", "c"], 18),  # two on podium, wrong spots + one exact
        (["a", "x", "y"], ["a", "b", "c"], 10),
        (["x", "y", "a"], ["a", "b", "c"], 4),
        (["x", "y", "z"], ["a", "b", "c"], 0),
    ],
)
def test_score_pick(pick, podium, points):
    assert game.score_pick(pick, podium) == points


def test_nicknames():
    assert game.valid_nickname("Lights Out")
    assert game.valid_nickname("max_33")
    for bad in ("ab", "x" * 21, "<script>", " lead", "the model"):
        assert not game.valid_nickname(bad)
    token, h = game.new_token()
    assert game.hash_token(token) == h and token not in h
