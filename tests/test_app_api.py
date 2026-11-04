"""Control application backend: API, process control (start/pause/resume/stop, one simulation at a time),
errors, exports. Real SUMO runs, shortened (2 to 10 simulated minutes). Requires fastapi + httpx."""
from __future__ import annotations

import csv
import io
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from agents.common.sim_env import BEGIN  # noqa: E402
from app.backend import results  # noqa: E402
from app.backend.server import create_app  # noqa: E402
from app.backend.sim_manager import SimulationManager  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "OUTPUT", tmp_path)            # runs created by the tests stay in tmp
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    with TestClient(create_app(mgr)) as c:
        c.mgr = mgr
        yield c
    if mgr._thread is not None and mgr._thread.is_alive():
        mgr.stop()


def wait_status(c, wanted, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get("/api/sim/state").json()
        if st["status"] in wanted:
            return st
        time.sleep(0.2)
    raise AssertionError(f"status {st['status']} never reached {wanted}")


def test_config_network_health(client):
    assert client.get("/api/health").json()["ok"] is True
    cfg = client.get("/api/config").json()
    ids = [s["id"] for s in cfg["strategies"]]
    assert {"S0_fixed_time", "S1_actuated", "S2_demand_gap", "S3_rl_qlearning"} <= set(ids)
    net = client.get("/api/network").json()
    assert len(net["signals"]) == 4 and len(net["lanes"]) > 50 and net["data_origin"].startswith("SIMULATED")


def test_full_short_run_writes_outputs_and_is_listed(client):
    st = client.mgr.start(strategy="S2_demand_gap", scale=2.0, seed=3, end=BEGIN + 600)
    assert st["status"] in ("starting", "running")
    st = client.mgr.wait(120)
    assert st["status"] == "finished", st.get("error")
    assert st["final_kpis"]["strategy"] == "S2_demand_gap" and st["live"]["vehicles"] >= 0
    assert len(st["signals"]) == 4 and all("state" in v for v in st["signals"].values())
    runs = client.get("/api/runs").json()["runs"]
    run = next(r for r in runs if r["id"] == st["run_id"])
    assert "decisions.csv" in run["files"] and run["source"] == "application"
    r = client.get(f"/api/runs/{run['id']}/files/decisions.csv")
    assert r.status_code == 200 and r.text.startswith("time_s;tls")
    exp = client.get("/api/export/kpi_runs.csv")
    rows = list(csv.DictReader(io.StringIO(exp.text), delimiter=";"))
    assert len(rows) == len(runs) and rows[0]["data_origin"].startswith("SIMULATED")


def test_pause_resume_stop_and_single_simulation(client):
    r = client.post("/api/sim/start", json={"strategy": "S0_fixed_time", "scale": 1, "seed": 1, "delay_ms": 20})
    assert r.status_code == 200
    wait_status(client, {"running"})
    assert client.post("/api/sim/start", json={"strategy": "S0_fixed_time"}).status_code == 409   # one at a time
    time.sleep(1.0)
    assert client.post("/api/sim/pause").json()["status"] == "paused"
    t1 = client.get("/api/sim/state").json()["sim_time"]
    time.sleep(1.0)
    t2 = client.get("/api/sim/state").json()["sim_time"]
    assert t2 - t1 <= 5.0                                    # at most one sample in flight when pausing
    assert client.post("/api/sim/resume").json()["status"] == "running"
    time.sleep(1.0)
    assert client.get("/api/sim/state").json()["sim_time"] > t2
    st = client.post("/api/sim/stop").json()
    assert st["status"] == "stopped" and st["final_kpis"]["stopped_early"] is True
    assert (results.OUTPUT / st["run_id"] / "kpis.json").exists()  # partial run still written
    assert client.post("/api/sim/stop").status_code == 409


def test_errors_are_explicit(client):
    assert client.post("/api/sim/start", json={"strategy": "S9_unknown"}).status_code == 400
    assert client.post("/api/sim/start", json={"scale": 50}).status_code == 422
    assert client.post("/api/sim/pause").status_code == 409
    assert client.get("/api/runs/../../etc/files/kpis.json").status_code == 404
    assert client.get("/api/reports/../../secret.md").status_code == 404
    assert client.get("/api/compare", params={"a": "S0_fixed_time", "b": "nothing", "scale": 5}).status_code == 404


def test_compare_and_reports_on_project_results():
    c = TestClient(create_app(SimulationManager()))
    r = c.get("/api/compare", params={"a": "S0_fixed_time", "b": "S1_actuated", "scale": 5})
    if r.status_code == 404:
        pytest.skip("evaluation runs not present")
    d = r.json()
    assert d["a"]["n"] >= 3 and d["b"]["n"] >= 3
    tt = next(x for x in d["rows"] if x["kpi"] == "avg_travel_time_s")
    assert tt["b_mean"] < tt["a_mean"] and tt["verdict"] in ("meilleur", "non significatif")
    rep = c.get("/api/reports").json()["reports"]
    assert rep and c.get(f"/api/reports/{rep[0]}").status_code == 200
    ds = c.get("/api/data-sources").json()
    assert any(s["origin"] == "simulée" for s in ds["sources"]) and any(s["origin"] == "réelle" for s in ds["sources"])
