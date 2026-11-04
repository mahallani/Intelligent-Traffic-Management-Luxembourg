"""Ambulance tracking (2026-10-22): status / next signal / events exposed to the application, sumo-gui drawing
commands, and the guarantee that the tracker only observes and draws (never touches signals or vehicle dynamics).
SIMULATED (SUMO, LuST demand)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.intervention.ambulance_tracker import COLOR, TLS_LABELS, AmbulanceTracker


class _Recorder:
    """Fake TraCI domain: records every call; getters come from `values` (callable or constant)."""

    def __init__(self, name, log, values=None, fail=()):
        self._name, self._log, self._values, self._fail = name, log, values or {}, set(fail)

    def __getattr__(self, attr):
        def call(*a):
            self._log.append(f"{self._name}.{attr}")
            if attr in self._fail:
                raise RuntimeError("view not available")
            v = self._values.get(attr)
            return v(*a) if callable(v) else v
        return call


def _fake_env(gui_fail=()):
    log, clock = [], {"t": 0.0}
    tl = "-28692"

    def departed():
        return ["ambulance"] if clock["t"] == 2 else []

    def arrived():
        return ["ambulance"] if clock["t"] == 6 else []

    def next_tls(_v):
        return [(tl, 3, 120.0 if clock["t"] < 4 else 20.0, "r")] if clock["t"] < 5 else [("-23354", 1, 300.0, "G")]
    polys = []
    api = SimpleNamespace(
        simulation=_Recorder("simulation", log, {"getDepartedIDList": departed, "getArrivedIDList": arrived, "getDeltaT": 1.0}),
        vehicle=_Recorder("vehicle", log, {"getDeparture": lambda v: 1.0, "getLaneID": "--31070#8_0", "getPosition": (1.0, 2.0),
                                            "getRoadID": "--31070#8", "getSpeed": 10.0, "getNextTLS": next_tls,
                                            "highlight": lambda *a: polys.append("ambulance_hl0")}),
        gui=_Recorder("gui", log, {"getIDList": ["View #0"], "getZoom": 100.0, "getOffset": (5.0, 6.0)}, fail=gui_fail),
        polygon=_Recorder("polygon", log, {"getIDList": lambda: tuple(polys)}),
        trafficlight=_Recorder("trafficlight", log))
    return SimpleNamespace(api=api), log, clock


def _run(tr, clock, steps=7):
    tr.inserted(0.0)
    for t in range(1, steps):
        clock["t"] = t
        tr.step(SimpleNamespace(time=float(t)))


def test_tracker_states_and_events_without_gui():
    env, log, clock = _fake_env()
    tr = AmbulanceTracker(env, gui=False)
    tr.inserted(0.0)
    assert tr.as_state()["status"] == "en attente d'insertion"
    for t in range(1, 7):
        clock["t"] = t
        tr.step(SimpleNamespace(time=float(t)))
        if t == 3:
            st = tr.as_state()
            assert st["status"] == "en circulation" and st["next"]["label"] == TLS_LABELS["-28692"] and st["next"]["dist_m"] == 120
    st = tr.as_state()
    assert st["status"] == "arrivée" and st["depart"] == "00:00:01" and st["arrival"] == "00:00:05" and st["travel_s"] == 4
    kinds = [e["event"] for e in tr.events]
    assert kinds == ["insertion demandée", "départ", "approche", "carrefour franchi", "sortie du réseau"]
    assert not any(c.startswith("gui.") or c.startswith("polygon.") for c in log)            # no drawing without GUI
    assert "vehicle.setColor" in log


@pytest.mark.parametrize("gui_fail", [(), ("trackVehicle",)])
def test_tracker_only_observes_and_draws(gui_fail):
    env, log, clock = _fake_env(gui_fail)
    tr = AmbulanceTracker(env, gui=True)
    _run(tr, clock)
    allowed_writes = {"vehicle.setColor", "vehicle.highlight", "polygon.setColor", "polygon.remove",
                      "gui.trackVehicle", "gui.setZoom", "gui.setOffset"}
    writes = {c for c in log if c.split(".")[1].startswith(("set", "add", "remove", "highlight", "track", "move", "change", "slow"))}
    assert writes <= allowed_writes, writes - allowed_writes                               # never a signal / speed / lane / route change
    assert not any(c.startswith("trafficlight.") for c in log)
    assert ("gui.trackVehicle" in log) and ("vehicle.highlight" in log)                      # camera asked, ring drawn
    assert tr.as_state()["status"] == "arrivée"                                             # a GUI failure never stops tracking
    if gui_fail:   # camera refused by sumo-gui: error recorded, no zoom (it only makes sense with tracking)
        assert any(g.startswith("suivi caméra") for g in tr.gui_errors)
    else:
        assert "gui.setZoom" in log and not tr.gui_errors


def test_color_is_the_documented_magenta():
    assert COLOR == (255, 0, 255, 255)


fastapi = pytest.importorskip("fastapi")


def test_ambulance_live_state_in_the_application(tmp_path):
    """Short app run (07:00-07:25) with the Windows reference settings: S0, x5, seed 1, ambulance with priority."""
    from app.backend.sim_manager import SimulationManager
    mgr = SimulationManager(runs_dir=tmp_path / "app_runs")
    mgr.start(strategy="S0_fixed_time", scale=5, seed=1, ambulance=True, ambulance_priority=True, end=26700.0)
    st = mgr.wait(170)
    assert st["status"] == "finished", st.get("error")
    e = st["emergency_live"]
    assert e["status"] == "arrivée" and e["depart"] == "07:20:17" and e["arrival"] == "07:23:26" and e["travel_s"] == 189
    assert st["final_kpis"]["emergency"]["travel_time_s"] == 189.0 and st["final_kpis"]["safety"]["total_violations"] == 0
    kinds = [x["event"] for x in e["events"]]
    assert kinds.count("approche") == 4 and kinds.count("demande de priorité") == 4 and kinds.count("carrefour franchi") == 4
    assert {x["carrefour"] for x in e["events"] if x["event"] == "approche"} == set(TLS_LABELS.values())
    import csv
    run = tmp_path / "app_runs" / st["run_id"].split("/", 1)[1]
    with open(run / "ambulance_events.csv", encoding="utf-8") as fh:            # timeline file (2026-10-22, step 2)
        rows = list(csv.DictReader(fh, delimiter=";"))
    assert [r["event"] for r in rows] == [x["event"] for x in reversed(e["events"])]
    assert rows[0]["event"] == "insertion demandée" and rows[-1]["event"] == "sortie du réseau"
    assert all(r["data_origin"].startswith("SIMULATED") for r in rows)
