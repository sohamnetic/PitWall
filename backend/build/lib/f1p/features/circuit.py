"""Circuit features: layout type, how processional races are there, driver track record."""

from __future__ import annotations

import pandas as pd
from scipy.stats import spearmanr

from f1p.features.tables import Tables

CIRCUIT_TYPE = {
    # Street and semi-permanent tracks: walls, few overtakes, safety cars.
    "monaco": "street", "marina_bay": "street", "baku": "street", "jeddah": "street",
    "vegas": "street", "miami": "street", "albert_park": "street", "villeneuve": "street",
    "sochi": "street", "madring": "street",
    # Low-drag, long straights.
    "monza": "high_speed", "spa": "high_speed", "red_bull_ring": "high_speed",
    "silverstone": "high_speed", "ricard": "high_speed", "losail": "high_speed",
    "rodriguez": "high_speed",
    # Twisty, high-downforce.
    "hungaroring": "high_downforce", "zandvoort": "high_downforce", "catalunya": "high_downforce",
    "imola": "high_downforce", "suzuka": "high_downforce", "portimao": "high_downforce",
    "mugello": "high_downforce",
    # Everything else: mixed layouts.
    "bahrain": "balanced", "yas_marina": "balanced", "americas": "balanced",
    "interlagos": "balanced", "shanghai": "balanced", "sepang": "balanced",
    "hockenheimring": "balanced", "istanbul": "balanced", "nurburgring": "balanced",
}  # fmt: skip
CIRCUIT_TYPES = ("street", "high_speed", "high_downforce", "balanced")

RHO_PRIOR_WEIGHT = 3.0  # pseudo-races pulling a circuit's mean towards the global mean


def race_grid_rho(t: Tables) -> pd.Series:
    """Spearman correlation of grid vs finish (classified, non-pit-lane) for each past race."""
    r = t.results[(t.results["session"] == "R") & t.results["classified"] & (t.results["grid"] > 0)]
    if r.empty:
        return pd.Series(dtype=float)

    def rho(g):
        return spearmanr(g["grid"], g["position"]).statistic if len(g) > 4 else float("nan")

    return r.groupby("race_id")[["grid", "position"]].apply(rho).dropna()


def circuit_features(t: Tables) -> pd.DataFrame:
    """Per race: circuit type and shrunk mean grid-finish correlation from earlier races."""
    races = t.races.sort_values("race_idx")
    rho = races["id"].map(race_grid_rho(t))
    rows = []
    for i, race in enumerate(races.itertuples()):
        prior = races.iloc[:i]
        prior_rho = rho.iloc[:i].dropna()
        global_mean = prior_rho.mean() if len(prior_rho) else 0.75
        here = prior_rho[prior["circuit_id"].loc[prior_rho.index] == race.circuit_id]
        rows.append(
            {
                "race_id": race.id,
                "circuit_type": CIRCUIT_TYPE.get(race.circuit_id, "balanced"),
                "circuit_grid_rho": (here.sum() + RHO_PRIOR_WEIGHT * global_mean)
                / (len(here) + RHO_PRIOR_WEIGHT),
                "circuit_races": len(here),
            }
        )
    return pd.DataFrame(rows).set_index("race_id")


def driver_circuit_features(panel: pd.DataFrame, races: pd.DataFrame) -> pd.DataFrame:
    """Driver's mean finishing pct at this circuit in earlier races."""
    p = panel.merge(races[["id", "circuit_id"]], left_on="race_id", right_on="id", how="left")
    p.index = panel.index
    g = p.groupby(["driver_id", "circuit_id"])["cls_pct"]
    total = g.transform(lambda s: s.shift(1).fillna(0).cumsum())
    count = g.transform(lambda s: s.shift(1).notna().cumsum())
    return pd.DataFrame(
        {"drv_circuit_pct": (total / count).where(count > 0), "drv_circuit_n": count},
        index=panel.index,
    )
