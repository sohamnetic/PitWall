"""History features from earlier races: form, teammate deltas, reliability, championship.

All values come from races strictly before the one being predicted: every series is
``shift(1)``-ed within its group before smoothing.
"""

from __future__ import annotations

import pandas as pd

from f1p.features.tables import DID_NOT_START_CODES, DNF_CODES, Tables

FORM_HALFLIFE = 4  # races
DNF_WINDOW = 10  # races
DNF_PRIOR, DNF_PRIOR_WEIGHT = 0.15, 5.0

# Rebrands of the same team, so form carries over a name change.
TEAM_LINEAGE = {
    "toro_rosso": "rb", "alphatauri": "rb", "rb": "rb",
    "force_india": "aston_martin", "racing_point": "aston_martin", "aston_martin": "aston_martin",
    "sauber": "audi", "alfa": "audi", "audi": "audi",
    "lotus_f1": "alpine", "renault": "alpine", "alpine": "alpine",
    "marussia": "manor", "manor": "manor",
}  # fmt: skip


def team_lineage(constructor_id: pd.Series) -> pd.Series:
    return constructor_id.map(TEAM_LINEAGE).fillna(constructor_id)


def _prior_ewm(df: pd.DataFrame, keys, col: str, halflife: float = FORM_HALFLIFE) -> pd.Series:
    return df.groupby(keys, sort=False)[col].transform(
        lambda s: s.shift(1).ewm(halflife=halflife, ignore_na=True).mean()
    )


def _prior_rolling_sum(df: pd.DataFrame, keys, col: str, window: int) -> pd.Series:
    return df.groupby(keys, sort=False)[col].transform(
        lambda s: s.shift(1).rolling(window, min_periods=1).sum()
    )


def race_panel(t: Tables, entries: pd.DataFrame) -> pd.DataFrame:
    """One row per (race, driver) for every past race plus the requested entries.

    Adds the per-race outcome columns the history features are built from. Rows for races
    without a result yet have NaN outcomes.
    """
    res = t.results[t.results["session"] == "R"]
    cols = ["race_id", "driver_id", "constructor_id"]
    panel = pd.concat([res[cols], entries[cols]]).drop_duplicates(["race_id", "driver_id"])
    panel = panel.merge(
        res[["race_id", "driver_id", "position", "position_text", "position_order", "points"]],
        on=["race_id", "driver_id"],
        how="left",
    ).merge(t.races[["id", "race_idx", "season", "regs_era"]], left_on="race_id", right_on="id")
    panel = panel.drop(columns="id")

    has_result = panel["position_text"].notna()
    panel["started"] = has_result & ~panel["position_text"].isin(DID_NOT_START_CODES)
    panel["dnf"] = panel["position_text"].isin(DNF_CODES).astype(float).where(panel["started"])
    n_started = panel.groupby("race_id")["started"].transform("sum")
    denom = (n_started - 1).clip(lower=1)
    # Finishing order as 0 (won) .. 1 (last), DNFs included at their sheet position.
    panel["pos_pct"] = ((panel["position_order"] - 1) / denom).where(panel["started"])
    # Same, classified finishers only: a cleaner pace signal.
    panel["cls_pct"] = ((panel["position"] - 1) / denom).where(panel["position"].notna())

    q = t.qualifying.copy()
    q["quali_pct"] = (q["position"] - 1) / (q.groupby("race_id")["position"].transform("max") - 1)
    panel = panel.merge(
        q[["race_id", "driver_id", "quali_pct"]], on=["race_id", "driver_id"], how="left"
    )

    panel["lineage"] = team_lineage(panel["constructor_id"])
    return panel.sort_values(["race_idx", "driver_id"]).reset_index(drop=True)


def _teammate_delta(panel: pd.DataFrame, col: str) -> pd.Series:
    """Own value minus the mean of teammates' values in the same race."""
    g = panel.groupby(["race_id", "constructor_id"])[col]
    total, count = g.transform("sum"), g.transform("count")
    others = (total - panel[col].fillna(0)) / (count - panel[col].notna().astype(int))
    return (panel[col] - others).where(panel[col].notna() & (count > 1))


def driver_features(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel
    out = pd.DataFrame(index=p.index)
    out["drv_form"] = _prior_ewm(p, "driver_id", "pos_pct")
    out["drv_pace_form"] = _prior_ewm(p, "driver_id", "cls_pct")
    out["drv_quali_form"] = _prior_ewm(p, "driver_id", "quali_pct")
    out["drv_last_pos_pct"] = p.groupby("driver_id")["pos_pct"].shift(1)

    tmp = p.assign(q_delta=_teammate_delta(p, "quali_pct"), r_delta=_teammate_delta(p, "cls_pct"))
    out["tm_quali_delta"] = _prior_ewm(tmp, "driver_id", "q_delta")
    out["tm_race_delta"] = _prior_ewm(tmp, "driver_id", "r_delta")

    started = p["started"].astype(float)
    out["drv_starts"] = (
        p.groupby("driver_id")["started"]
        .transform(lambda s: s.astype(float).shift(1).cumsum())
        .fillna(0)
    )
    out["seat_starts"] = (
        p.assign(_s=started)
        .groupby(["driver_id", "lineage"])["_s"]
        .transform(lambda s: s.shift(1).cumsum())
        .fillna(0)
    )

    dnfs = _prior_rolling_sum(p.assign(_d=p["dnf"].astype(float)), "driver_id", "_d", DNF_WINDOW)
    starts = _prior_rolling_sum(
        p.assign(_s=p["dnf"].notna().astype(float)), "driver_id", "_s", DNF_WINDOW
    )
    out["drv_dnf_rate"] = (dnfs.fillna(0) + DNF_PRIOR * DNF_PRIOR_WEIGHT) / (
        starts.fillna(0) + DNF_PRIOR_WEIGHT
    )
    return out


def team_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Team form from the lineage's per-race averages, across all eras and within the era."""
    team_race = (
        panel.groupby(["lineage", "race_id", "race_idx", "regs_era"], as_index=False)
        .agg(
            pos_pct=("pos_pct", "mean"),
            cls_pct=("cls_pct", "mean"),
            quali_pct=("quali_pct", "mean"),
            dnfs=("dnf", "sum"),
            dnf_n=("dnf", "count"),
        )
        .sort_values("race_idx")
    )
    tr = team_race
    feats = pd.DataFrame({"lineage": tr["lineage"], "race_id": tr["race_id"]})
    feats["team_form"] = _prior_ewm(tr, "lineage", "pos_pct")
    feats["team_pace_form"] = _prior_ewm(tr, "lineage", "cls_pct")
    feats["team_quali_form"] = _prior_ewm(tr, "lineage", "quali_pct")
    # Within the current regulation era only: NaN at the first race of a new era.
    feats["team_era_form"] = _prior_ewm(tr, ["lineage", "regs_era"], "cls_pct")
    feats["team_era_quali_form"] = _prior_ewm(tr, ["lineage", "regs_era"], "quali_pct")
    feats["team_era_races"] = tr.groupby(["lineage", "regs_era"]).cumcount()

    dnfs = _prior_rolling_sum(tr, "lineage", "dnfs", DNF_WINDOW)
    n = _prior_rolling_sum(tr, "lineage", "dnf_n", DNF_WINDOW)
    feats["team_dnf_rate"] = (dnfs.fillna(0) + DNF_PRIOR * DNF_PRIOR_WEIGHT) / (
        n.fillna(0) + DNF_PRIOR_WEIGHT
    )
    return (
        panel[["lineage", "race_id"]]
        .merge(feats, on=["lineage", "race_id"], how="left")
        .drop(columns=["lineage", "race_id"])
        .set_index(panel.index)
    )


def championship_features(t: Tables, panel: pd.DataFrame) -> pd.DataFrame:
    """Points scored earlier in the season (races + sprints) and rank among this race's entries."""
    pts = (
        t.results.dropna(subset=["points"])
        .groupby(["race_id", "driver_id"], as_index=False)["points"]
        .sum()
    )
    p = panel[["race_id", "driver_id", "race_idx", "season"]].merge(
        pts, on=["race_id", "driver_id"], how="left"
    )
    p["points"] = p["points"].fillna(0)
    p = p.sort_values("race_idx")
    p["season_pts_before"] = p.groupby(["driver_id", "season"])["points"].transform(
        lambda s: s.cumsum().shift(1).fillna(0)
    )
    out = p.sort_index()[["season_pts_before"]]
    out["champ_rank_pct"] = (
        out.groupby(panel["race_id"])["season_pts_before"].rank(ascending=False, method="min") - 1
    ) / (panel.groupby("race_id")["driver_id"].transform("count") - 1).clip(lower=1)
    return out
