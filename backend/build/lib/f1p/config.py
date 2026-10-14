"""Project-wide settings: paths, season ranges and model parameters."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("F1P_DATA_DIR", ROOT_DIR / "data"))
CACHE_DIR = DATA_DIR / "cache"
FASTF1_CACHE_DIR = CACHE_DIR / "fastf1"
JOLPICA_CACHE_DIR = CACHE_DIR / "jolpica"
LAPS_DIR = DATA_DIR / "laps"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = Path(os.environ.get("F1P_DB_PATH", DATA_DIR / "f1p.sqlite"))

JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"

# Hybrid era onward for results; FastF1 lap timing is reliable from 2018.
RESULTS_FIRST_SEASON = 2014
LAPS_FIRST_SEASON = 2018

# Regulation eras: first season of each technical rule set.
REGULATION_ERAS = {
    2014: "hybrid-v1",
    2017: "hybrid-wide",
    2022: "ground-effect",
    2026: "active-aero",
}

# Training sample weights: exponential decay by age plus a boost for the current era.
SAMPLE_WEIGHT_HALF_LIFE_RACES = 30
CURRENT_ERA_WEIGHT_BOOST = 3.0

N_SIMULATIONS = 10_000
POINTS_POSITIONS = 10


def regulation_era(season: int) -> str:
    """Return the regulation era a season belongs to."""
    start = max(y for y in REGULATION_ERAS if y <= season)
    return REGULATION_ERAS[start]


def ensure_dirs() -> None:
    for d in (DATA_DIR, FASTF1_CACHE_DIR, JOLPICA_CACHE_DIR, LAPS_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
