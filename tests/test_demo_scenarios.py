"""Demo scenarios of the Design-Thinking prototype (2026-10-22): simulated incident and ambulance launched from the
application API, faithful decision explanations, forecasts checked against observed values, 8-seed comparison.
All runs are SIMULATED (SUMO, LuST demand); short runs are used to keep the suite fast."""
from __future__ import annotations

import csv
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from agents.common.sim_env import BEGIN  # noqa: E402
from app.backend import results  # noqa: E402
from app.backend.server import create_app  # noqa: E402
from app.backend.sim_manager import INCIDENTS, SimulationManager  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "OUTPUT", tmp_path)
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    with TestClient(create_app(mgr)) as c:
        c.mgr = mgr
        yield c
    if mgr._thread is not None and mgr._thread.is_alive():
        mgr.stop()


def test_incident_and_ambulance_from_the_api(client):
    """Scenario B: blocked lane before Carrefour 4 at 07:20 + ambulance with priority, launched like the UI does."""
    r = client.post("/api/sim/start", json={"strategy": "S2_demand_gap", "scale": 5, "seed": 61, "incident": "carrefour4",
                                            "ambulance": True, "ambulance_priority": True})
    assert r.status_code == 200 and r.json()["incident"]["lane"] == INCIDENTS["carrefour4"]["lane"]
    st = client.mgr.wait(170)
    assert st["status"] == "finished", st.get("error")
    k = st["final_kpis"]
    assert k["incident"]["detected"] is True and k["incident"]["applied_at"] == 26400.0 and k["incident"]["removed_at"] == 27600.0
    assert k["emergency"]["priority"] is True and k["emergency"]["travel_time_s"] is not None
    assert k["safety"]["total_violations"] == 0
    assert any(a["lane"].split("_")[0] == "-31070#4" for a in st["alerts"])          # alert on the incident edge
    assert "_incident_carrefour4_ambulance_prio" in st["run_id"]


def test_unknown_incident_is_refused(client):
    assert client.post("/api/sim/start", json={"incident": "nowhere"}).status_code == 400


def test_decisions_carry_the_recorded_explanation(client, tmp_path):
    """Every phase change is written with the inputs the controller really used (or the safety rule)."""
    st = client.post("/api/sim/start", json={"strategy": "S3_rl_qlearning", "scale": 5, "seed": 62}).json()
    st = client.mgr.wait(170)
    assert st["status"] == "finished", st.get("error")
    run = tmp_path / "app_runs" / st["run_id"].split("/", 1)[1]
    with open(run / "decisions.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert rows and list(rows[0])[-1] == "explanation"
    sources = set()
    for r in rows:
        ex = json.loads(r["explanation"])
        if r["reason"] == "max_green":
            assert ex["source"].startswith("sécurité") and ex["vert_s"] >= ex["limite_s"] - 1e-6
        else:
            assert ex["action"] == "passer"                       # only phase changes are logged
            if ex["source"] == "table apprise":                  # learned: the chosen action has the higher Q value
                assert ex["q_passer"] > ex["q_garder"] and min(ex["visites_garder_passer"]) >= 3
            else:
                assert ex["source"].startswith("règle de secours") and ex["règle_S2"]["action"] == "passer"
        sources.add(ex["source"].split(" (")[0])
    assert {"table apprise", "règle de secours S2", "sécurité : vert maximum atteint"} <= sources


def test_forecasts_are_checked_against_observations(client):
    st = client.post("/api/sim/start", json={"strategy": "S0_fixed_time", "scale": 3, "seed": 5}).json()
    st = client.mgr.wait(170)
    assert st["status"] == "finished", st.get("error")
    sc = st["final_kpis"]["prediction"]
    assert all(sc.get(f"mae_cascade_{h}min") is not None for h in (5, 10, 15))
    checks = st["prediction_checks"]
    assert checks and all(abs(c["forecast"] - c["observed"] - c["error"]) < 0.02 for c in checks)


def test_comparison_uses_the_8_evaluation_seeds(client):
    res = client.get("/api/compare", params={"a": "S0_fixed_time", "b": "S3_rl_qlearning", "scale": 5}).json()
    assert res["a"]["seeds"] == [1, 2, 3, 61, 62, 63, 64, 65] and res["b"]["seeds"] == res["a"]["seeds"]
