import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from f1p.models.calibrate import fit_temperature
from f1p.models.simulate import plackett_luce_loglik, simulate


def test_simulate_probabilities_are_consistent():
    probs = simulate(np.array([2.0, 1.0, 0.0, -1.0]), np.array([0.1, 0.1, 0.1, 0.1]), 1.0, 20_000)
    np.testing.assert_allclose(probs.sum(axis=0), 1, atol=1e-9)
    np.testing.assert_allclose(probs.sum(axis=1), 1, atol=1e-9)
    assert probs[0, 0] > probs[1, 0] > probs[2, 0] > probs[3, 0]


def test_simulate_matches_plackett_luce_win_probability():
    scores, t = np.array([1.0, 0.5, 0.0]), 0.7
    probs = simulate(scores, np.zeros(3), t, 200_000)
    exact = np.exp(scores / t) / np.exp(scores / t).sum()
    np.testing.assert_allclose(probs[:, 0], exact, atol=0.005)


def test_certain_retirement_finishes_last():
    probs = simulate(np.array([5.0, 0.0, -1.0]), np.array([1.0, 0.0, 0.0]), 1.0, 5000)
    assert probs[0, 2] == 1.0


def test_plackett_luce_loglik_two_drivers():
    # P(a beats b) = e^1 / (e^1 + e^0)
    ll = plackett_luce_loglik(np.array([1.0, 0.0]), np.array([0, 1]), 1.0)
    assert ll == pytest.approx(np.log(np.e / (np.e + 1)))
    assert plackett_luce_loglik(np.array([1.0, 0.0, 3.0]), np.array([2, 0, 1]), 1.0, top_k=1) == (
        pytest.approx(3 - np.log(np.exp(1) + 1 + np.exp(3)))
    )


def test_fit_temperature_recovers_true_noise():
    rng = np.random.default_rng(1)
    true_t, races = 2.0, []
    for _ in range(400):
        scores = rng.normal(0, 3, 10)
        order = np.argsort(-(scores / true_t + rng.gumbel(size=10)))  # exact PL draw
        races.append((scores, order))
    assert fit_temperature(races) == pytest.approx(true_t, rel=0.15)


@pytest.fixture
def synthetic_rows():
    """Feature rows where team form drives the finishing order."""
    from f1p.features.build import feature_columns

    rng = np.random.default_rng(0)
    rows = []
    for r in range(120):
        form = rng.random(10)
        finish = np.argsort(np.argsort(form + rng.normal(0, 0.15, 10))) + 1
        for d in range(10):
            row = {c: np.nan for c in feature_columns("post")}
            row.update(
                race_id=f"r{r}", race_idx=r, season=2024 + r // 40, driver_id=f"d{d}",
                team_form=form[d], team_era_form=form[d], drv_form=form[d], grid_pct=form[d],
                team_dnf_rate=0.1, drv_dnf_rate=0.1, circuit_type="balanced",
                team_era_races=10, finish_order=finish[d], finish_pos=float(finish[d]),
                dnf=0.0, started=1,
            )  # fmt: skip
            rows.append(row)
    df = pd.DataFrame(rows)
    df["circuit_type"] = pd.Categorical(df["circuit_type"])
    return df


def test_race_model_learns_signal_and_round_trips(synthetic_rows, tmp_path, monkeypatch):
    from f1p import config
    from f1p.models.race_model import RaceModel, model_path

    train = synthetic_rows[synthetic_rows.race_idx < 110]
    race = synthetic_rows[synthetic_rows.race_idx == 115].reset_index(drop=True)
    model = RaceModel("post", n_sims=4000).fit(train)
    pred = model.predict_race(race)
    # Lower form value = better; the predicted order should follow it closely.
    assert spearmanr(race["team_form"], pred.expected_pos).statistic > 0.85
    assert race["team_form"].idxmin() in np.argsort(-pred.p_win)[:3]
    np.testing.assert_allclose(pred.probs.sum(axis=0), 1, atol=1e-9)

    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    model.save(model_path("post"), trained_through="r109")
    loaded = RaceModel.load("post")
    assert loaded.meta["trained_through"] == "r109"
    np.testing.assert_allclose(loaded.predict_race(race).probs, pred.probs)
