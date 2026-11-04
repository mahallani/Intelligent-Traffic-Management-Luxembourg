"""Cascade multi-horizon prediction: no look-ahead, cascade structure, evaluation, transmission to the
decision agent and the on/off switch. SUMO runs are short (10 simulated minutes)."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from agents.common.sim_env import BEGIN
from agents.prediction import cascade as C
from agents.prediction.cascade_agent import DEFAULT_MODEL

MODEL_OK = DEFAULT_MODEL.exists()


def synthetic_episode(slope_per_min: float, n_min: int = 40, noise: float = 0.0, seed: int = 0):
    """5-s samples where every signal's halted vehicles grow linearly (known future)."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_min * 12):
        t = BEGIN + 1 + 5 * k
        v = max(0.0, slope_per_min * (t - BEGIN) / 60 + rng.normal(0, noise))
        rows.append({"time_s": t, "vehicles_in_network": 50, **{f"halting_{tl}": v for tl in C.TLS_CHAIN}})
    return rows


def test_features_use_only_the_past():
    rows = synthetic_episode(0.5)
    times = [r["time_s"] for r in rows]
    halt = {tl: [r[f"halting_{tl}"] for r in rows] for tl in C.TLS_CHAIN}
    veh = [r["vehicles_in_network"] for r in rows]
    t = BEGIN + 600
    f1 = C.features_at(times, halt, veh, t)
    cut = [i for i, x in enumerate(times) if x <= t]               # drop the future entirely
    f2 = C.features_at([times[i] for i in cut], {k: [v[i] for i in cut] for k, v in halt.items()}, [veh[i] for i in cut], t)
    assert f1 == f2


def test_targets_are_the_future_minute_means():
    s = C.episode_samples(synthetic_episode(1.0))
    r = s[0]
    for h in C.HORIZONS:
        # linear growth of 1 vehicle/min: the mean over the target minute is about origin+h minus 30 s
        expected = (r["origin"] + h - 30 - BEGIN) / 60
        assert r["y"][h] == pytest.approx(expected, abs=0.1)


def test_cascade_stages_take_previous_predictions_and_beat_persistence_on_a_trend():
    train = [C.episode_samples(synthetic_episode(s, noise=0.2, seed=i)) for i, s in enumerate((0.2, 0.4, 0.6, 0.8, 1.0))]
    m = C.fit(train, transform="none")
    nf = len(C.FEATURES)
    assert [len(m.cascade[str(h)]) for h in C.HORIZONS] == [nf, nf + 1, nf + 2]   # +10 uses y5, +15 uses y5 and y10
    test = C.episode_samples(synthetic_episode(0.7, noise=0.2, seed=99))
    for h in C.HORIZONS:
        mae = np.mean([abs(m.predict(r["x"])[h] - r["y"][h]) for r in test])
        pers = np.mean([abs(r["x"][0] - r["y"][h]) for r in test])
        assert mae < pers


def test_model_save_load_roundtrip(tmp_path):
    m = C.fit([C.episode_samples(synthetic_episode(0.5, seed=i, noise=0.1)) for i in range(3)])
    m.save(tmp_path / "m.json")
    m2 = C.CascadeModel.load(tmp_path / "m.json")
    x = C.episode_samples(synthetic_episode(0.5))[3]["x"]
    assert m.predict(x) == m2.predict(x) and m2.kind == m.kind


@pytest.mark.skipif(not MODEL_OK, reason="trained cascade model not present")
def test_online_agent_logs_forecast_observed_error_and_feeds_the_decision(tmp_path):
    from agents.orchestrator import run_episode
    from agents.decision.controllers import ForecastGapController

    seen = []

    class Spy(ForecastGapController):
        def decide(self, obs, env, forecasts=None):
            if forecasts:
                seen.append({t: dict(f) for t, f in forecasts.items()})
            return super().decide(obs, env, forecasts)

    k = run_episode("S2F_forecast_gap", 3.0, 7, tmp_path / "run", controller=Spy(), end=BEGIN + 1500)
    assert seen and set(seen[-1]) == set(C.TLS_CHAIN) and all({300, 600, 900} <= set(f) for f in seen[-1].values())
    with open(tmp_path / "run" / "predictions.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert rows and {"forecast", "observed", "error", "horizon_min"} <= set(rows[0])
    r = rows[0]
    assert float(r["error"]) == pytest.approx(float(r["forecast"]) - float(r["observed"]), abs=1e-3)
    assert k["prediction"]["n_scored"] == len(rows) and k["forecasts_passed_to_decision"] is True


@pytest.mark.skipif(not MODEL_OK, reason="trained cascade model not present")
def test_forecast_switch_off_gives_exactly_S2(tmp_path):
    from agents.orchestrator import run_episode
    a = run_episode("S2F_forecast_gap", 5.0, 8, tmp_path / "f_off", end=BEGIN + 900, use_forecast=False)
    b = run_episode("S2_demand_gap", 5.0, 8, tmp_path / "s2", end=BEGIN + 900)
    for key in ("avg_travel_time_s", "avg_waiting_time_s", "co2_kg", "arrived"):
        assert a[key] == b[key]
    assert a["forecasts_passed_to_decision"] is False
