"""What-if scenarios: re-run the post-qualifying model on a hypothetical starting grid.

The user can reorder the grid, send drivers to the pit lane, rule drivers out of the race,
force a retirement, or make the race more chaotic. Only the inputs the scenario touches
change; every other feature (form, practice pace, circuit) stays exactly as the model sees it.

Before qualifying there is no real grid, so a hypothetical one also stands in for qualifying:
each driver gets the typical qualifying gap for their hypothetical slot. After qualifying,
real qualifying pace is kept and only the grid moves (as with a grid penalty).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from f1p.features.tables import Tables

CHAOS_RANGE = (0.5, 3.0)


@dataclass
class Scenario:
    grid: list[str] | None = None  # starting order, P1 first; None = keep the current grid
    pit_lane: list[str] = field(default_factory=list)  # start from the pit lane (back)
    out: list[str] = field(default_factory=list)  # not taking part
    retire: list[str] = field(default_factory=list)  # certain to retire
    chaos: float = 1.0  # multiplies the model's randomness (rain, safety cars, ...)

    def is_noop(self) -> bool:
        return (
            self.grid is None
            and not self.pit_lane
            and not self.out
            and not self.retire
            and self.chaos == 1.0
        )


class ScenarioError(ValueError):
    pass


def typical_quali_gaps(t: Tables, seasons: int = 3) -> pd.Series:
    """Median gap to pole (%) by qualifying position over the most recent seasons."""
    q = t.qualifying.merge(t.races[["id", "season"]], left_on="race_id", right_on="id")
    q = q[q["season"] > q["season"].max() - seasons].copy()
    best = q[["q1_s", "q2_s", "q3_s"]].astype(float).min(axis=1)
    q["gap"] = (best / best.groupby(q["race_id"]).transform("min") - 1) * 100
    return q.groupby("position")["gap"].median()


def apply(rows: pd.DataFrame, s: Scenario, quali_gaps: pd.Series) -> pd.DataFrame:
    """Return post-qualifying feature rows modified by the scenario."""
    ids = list(rows["driver_id"])
    for name, group in (("pit lane", s.pit_lane), ("out", s.out), ("retire", s.retire)):
        unknown = set(group) - set(ids)
        if unknown:
            raise ScenarioError(f"not in this race ({name}): {', '.join(sorted(unknown))}")
    if not CHAOS_RANGE[0] <= s.chaos <= CHAOS_RANGE[1]:
        raise ScenarioError(f"chaos must be between {CHAOS_RANGE[0]} and {CHAOS_RANGE[1]}")

    rows = rows[~rows["driver_id"].isin(s.out)].copy().reset_index(drop=True)
    ids = list(rows["driver_id"])
    n = len(rows)
    if n < 2:
        raise ScenarioError("at least two drivers must race")

    if s.grid is not None:
        if sorted(set(s.grid) - set(s.out)) != sorted(ids) or len(s.grid) != len(set(s.grid)):
            raise ScenarioError("the grid must list every racing driver exactly once")
        order = [d for d in s.grid if d not in s.out]
    else:
        current = rows["grid_pct"].fillna(rows["quali_pos_pct"])
        if current.isna().all():
            raise ScenarioError("no grid yet: provide a starting order")
        order = list(rows.assign(_g=current).sort_values("_g", na_position="last")["driver_id"])

    # Pit-lane starters go to the back in the order given; everyone else closes up.
    racing = [d for d in order if d not in s.pit_lane] + [d for d in order if d in s.pit_lane]
    slot = {d: i + 1 for i, d in enumerate(racing)}
    pos = rows["driver_id"].map(slot).astype(float)
    rows["grid_pct"] = (pos - 1) / max(n - 1, 1)
    rows["pitlane_start"] = rows["driver_id"].isin(s.pit_lane).astype(float)

    if rows["quali_pos_pct"].isna().all():
        # Before qualifying: the hypothetical grid doubles as the qualifying result.
        quali_pos = rows["driver_id"].map({d: i + 1 for i, d in enumerate(order)}).astype(float)
        rows["quali_pos_pct"] = (quali_pos - 1) / max(n - 1, 1)
        rows["quali_gap_pct"] = quali_pos.map(quali_gaps).fillna(quali_gaps.max())
    rows["grid_x_rho"] = rows["grid_pct"] * rows["circuit_grid_rho"]
    return rows


def simulation_inputs(model, rows: pd.DataFrame, s: Scenario):
    """Scores, retirement chances and temperature for the scenario's simulated races."""
    scores = model.ranker.score(rows)
    p_dnf = model.dnf.predict(rows)
    p_dnf = np.where(rows["driver_id"].isin(s.retire), 1.0, p_dnf)
    return scores, p_dnf, model.temperature * s.chaos
