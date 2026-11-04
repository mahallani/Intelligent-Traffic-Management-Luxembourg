"""SUMO launch and process life cycle through TraCI (bug of 2026-10-15: "Could not connect to TraCI server using
port ... (TraCI server already finished). Retrying with different port." repeated ~60 times, empty run folder,
SUMO's error never shown). All tests force the TraCI backend (SUMO in a subprocess), the one used on Windows
when libsumo cannot be loaded."""
from __future__ import annotations

import json
import sys
import time

import pytest

from agents.common.sim_env import BEGIN, SimEnv
from traci_layer import config as C
from traci_layer.launcher import SumoStartError, describe_returncode, start_traci


@pytest.fixture()
def traci_backend(monkeypatch):
    monkeypatch.setenv("ITM_SUMO_BACKEND", "traci")


@pytest.fixture()
def broken_sumo(monkeypatch):
    """SUMO refuses to start (unknown option): it prints an error and exits at once - the reported situation."""
    orig = C.SumoConfig.build_command
    monkeypatch.setattr(C.SumoConfig, "build_command", lambda self: orig(self) + ["--option-that-does-not-exist", "1"])


def test_sumo_dying_at_start_fails_fast_with_its_own_message(tmp_path, traci_backend, broken_sumo):
    """Reproduces the case: before the fix, 61 SUMO launches in ~60 s and a bare 'Could not connect'."""
    env = SimEnv(out_dir=tmp_path / "run", end=BEGIN + 10)
    t0 = time.time()
    with pytest.raises(SumoStartError) as ei:
        env.start()
    assert time.time() - t0 < 15
    e = ei.value
    assert e.launches == 1                                   # no relaunch on a non-port error
    assert e.returncode not in (None, 0)
    assert "option-that-does-not-exist" in e.output_tail      # SUMO's own message is kept
    log = (tmp_path / "run" / "sumo_process.log").read_text(encoding="utf-8")
    assert "command:" in log and "--remote-port" in log and "SUMO exit" in log
    assert env.conn.process is None and env.api is None


def test_silent_crash_reports_the_exit_code(tmp_path):
    """A process that dies without writing anything (like a sumo-gui or DLL failure on Windows)."""
    cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
    with pytest.raises(SumoStartError) as ei:
        start_traci(cmd, "silent_test", process_log=tmp_path / "p.log")
    assert ei.value.returncode == 3 and ei.value.launches == 1
    assert "code 3" in str(ei.value)
    assert "0xC0000139" in describe_returncode(-1073741511)   # Windows 'entry point not found' is decoded


def test_application_reports_the_failure_and_recovers(tmp_path, traci_backend, monkeypatch):
    from app.backend.sim_manager import SimulationManager
    orig = C.SumoConfig.build_command
    monkeypatch.setattr(C.SumoConfig, "build_command", lambda self: orig(self) + ["--option-that-does-not-exist", "1"])
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    t0 = time.time()
    mgr.start(strategy="S0_fixed_time", end=BEGIN + 60)
    st = mgr.wait(30)
    assert st["status"] == "error" and time.time() - t0 < 20
    assert "SumoStartError" in st["error"] and "option-that-does-not-exist" in st["error_detail"]["sumo_output_tail"]
    run = tmp_path / "app_runs" / st["run_id"].split("/", 1)[1]
    err = json.loads((run / "app_error.json").read_text(encoding="utf-8"))
    assert err["launches"] == 1 and (run / "sumo_process.log").exists()
    monkeypatch.setattr(C.SumoConfig, "build_command", orig)  # SUMO repaired: the next start works
    mgr.start(strategy="S0_fixed_time", end=BEGIN + 60)
    st = mgr.wait(60)
    assert st["status"] == "finished", st.get("error")
    assert st["final_kpis"]["backend"] == "traci"


def test_full_simulation_over_traci_collects_kpis(tmp_path, traci_backend):
    """Complete 07:00-08:00 run (S0, x1) launched like the application on Windows (TraCI), KPIs collected."""
    from app.backend.sim_manager import SimulationManager
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    mgr.start(strategy="S0_fixed_time", scale=1.0, seed=1)
    with pytest.raises(Exception):
        mgr.start(strategy="S1_actuated")                     # one simulation at a time
    st = mgr.wait(170)
    assert st["status"] == "finished", st.get("error")
    k = st["final_kpis"]
    assert k["backend"] == "traci" and k["stopped_early"] is False and k["end"] == 28800.0
    assert k["arrived"] > 700 and 80 < k["avg_travel_time_s"] < 130 and k["co2_kg"] > 0
    assert k["safety"]["total_violations"] == 0
    run = tmp_path / "app_runs" / st["run_id"].split("/", 1)[1]
    for f in ("kpis.json", "tripinfo.xml", "summary.xml", "queue_timeseries.csv", "decisions.csv", "predictions.csv",
              "sumo.log", "sumo_process.log"):
        assert (run / f).exists(), f
    assert "TraCI requested termination" in (run / "sumo.log").read_text(encoding="utf-8")


def test_stop_and_shutdown_leave_no_sumo_process(tmp_path, traci_backend):
    from app.backend.sim_manager import SimulationManager
    import agents.common.sim_env as se
    procs = []
    orig_start = se.SimEnv.start

    def spy(self):
        api = orig_start(self)
        procs.append(self.conn.process)
        return api
    se.SimEnv.start = spy
    try:
        mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
        mgr.start(strategy="S2_demand_gap", scale=2.0, seed=4, delay_ms=5)
        time.sleep(3)
        assert mgr.state()["status"] in ("running", "starting")
        mgr.pause()
        time.sleep(1)
        mgr.resume()
        mgr.shutdown(wait_s=30)                               # what the backend does on Ctrl+C
        st = mgr.state()
        assert st["status"] == "stopped" and st["final_kpis"]["stopped_early"] is True
    finally:
        se.SimEnv.start = orig_start
    assert procs and all(p.poll() is not None for p in procs)  # SUMO really ended


def test_gui_start_refused_clearly_when_sumo_gui_cannot_start(tmp_path, monkeypatch):
    """Case diagnosed on the Windows PC on 15/10: sumo-gui.exe exits with 0xC0000135 (gdal.dll -> VCOMP140.DLL
    missing) while sumo.exe works. The application must refuse a GUI start at once with the reason, without
    creating an empty run, and still accept the same simulation without GUI."""
    import agents.common.sim_env as se
    from app.backend.sim_manager import SimulationManager
    fake = tmp_path / ("fake-sumo-gui.cmd" if sys.platform == "win32" else "fake-sumo-gui")
    if sys.platform == "win32":
        fake.write_text("@exit /b -1073741515\n")
    else:
        fake.write_text("#!/bin/sh\nexit 135\n")
        fake.chmod(0o755)
    import traci_layer.config as cfg
    real = cfg.find_sumo_binary
    monkeypatch.setattr(cfg, "find_sumo_binary", lambda gui=False: str(fake) if gui else real(False))
    monkeypatch.setattr(se, "_BINARY_OK", {})
    ok, msg = se.sumo_binary_status(True)
    assert not ok and "SUMO-GUI ne peut pas démarrer" in msg
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    with pytest.raises(ValueError, match="Décoche SUMO-GUI"):
        mgr.start(strategy="S0_fixed_time", gui=True, end=BEGIN + 30)
    assert not (tmp_path / "app_runs").exists() or not any((tmp_path / "app_runs").iterdir())
    assert mgr.state()["status"] == "idle"
    mgr.start(strategy="S0_fixed_time", gui=False, end=BEGIN + 30)
    assert mgr.wait(60)["status"] == "finished"
