"""
Integration tests on the REAL LuST Luxembourg scenario (dua.actuated.sumocfg).
Skipped automatically if LuSTScenario/ is not installed (run setup_lust.ps1).

They also pin down the facts stated in docs/TRACI_LAYER.md, so that the documentation
stays true if LuST or SUMO is upgraded.
"""
from __future__ import annotations

import pytest

from conftest import lust_available
from traci_layer import CollectorConfig, SumoConfig, SumoConnection, TrafficDataCollector
from traci_layer.bus_data import load_bus_plan
from traci_layer.config import DEFAULT_SUMOCFG, cfg_route_files
from traci_layer.simulation import SimulationController

pytestmark = lust_available


@pytest.fixture(scope="module")
def lust_run(tmp_path_factory):
    """First 180 s of the LuST day with full collection."""
    out = tmp_path_factory.mktemp("lust")
    with SumoConnection(SumoConfig(output_dir=out, label="lust_it")) as api:
        facts = {
            "vtypes": {t: api.vehicletype.getVehicleClass(t) for t in api.vehicletype.getIDList()
                       if not t.startswith("DEFAULT_")},
            "emission_classes": {t: api.vehicletype.getEmissionClass(t) for t in ("passenger1", "bus")},
            "tls": api.trafficlight.getIDList(),
            "logics": {t: api.trafficlight.getAllProgramLogics(t) for t in api.trafficlight.getIDList()},
            "busstops": api.busstop.getIDCount(),
            "e1": api.inductionloop.getIDCount(),
            "e2": api.lanearea.getIDCount(),
        }
        col = TrafficDataCollector(api, CollectorConfig(snapshot_interval=60), scenario="S0")
        obs = list(col.run(duration=180, observe_every=60))
        state = out / "lust_state.xml.gz"
        n_fixed = _save_raw_and_repair(api, state)
        facts["running"] = api.vehicle.getIDCount()
        facts["time"] = api.simulation.getTime()
        kpis = col.kpis()
    return facts, col, obs, kpis, state, n_fixed


def _save_raw_and_repair(api, path):
    from traci_layer.simulation import repair_state_file

    api.simulation.saveState(str(path))
    return repair_state_file(path)


def test_lust_vehicle_types_and_no_emergency(lust_run):
    facts = lust_run[0]
    classes = set(facts["vtypes"].values())
    assert facts["vtypes"]["bus"] == "bus"
    assert classes <= {"passenger", "bus"}, "LuST contains only cars and buses - no emergency vehicle"
    assert facts["emission_classes"]["passenger1"].startswith("HBEFA4/PC_petrol")
    assert facts["emission_classes"]["bus"].startswith("HBEFA4/UBus")


def test_lust_traffic_lights_are_effectively_fixed_time(lust_run):
    facts = lust_run[0]
    assert len(facts["tls"]) == 201
    for logics in facts["logics"].values():
        assert len(logics) == 1 and logics[0].programID == "0" and logics[0].type == 3  # actuated
        assert all(p.minDur == p.maxDur for p in logics[0].phases)  # ... but no actuation range


def test_lust_infrastructure_counts(lust_run):
    facts = lust_run[0]
    assert facts["busstops"] == 561
    assert facts["e1"] == 3146
    assert facts["e2"] == 0  # no lane-area detectors -> queue length must be computed


def test_lust_bus_plan():
    bus_files = [f for f in cfg_route_files(DEFAULT_SUMOCFG) if "bus" in f.name.lower()]
    plan = load_bus_plan(bus_files)
    assert len(plan) == 2240
    assert len({t.line for t in plan.values()}) == 38
    assert all(t.planned_headway for t in plan.values() if t.planned_headway is not None)


def test_lust_observation_content(lust_run):
    _, col, obs, kpis, *_ = lust_run
    assert len(obs) == 3
    o = obs[-1]
    assert o["meta"]["clock"] == "00:03:00"
    assert o["vehicles"]["count"] > 20  # 00:03, night traffic
    assert o["congestion"]["edges"]["edges_monitored"] == 5779
    assert o["congestion"]["tls_lanes"]["lanes_monitored"] > 1000
    assert o["traffic_lights"]["total_signals"] == 201
    assert o["buses"]["count"] > 0
    assert o["environment"]["co2_total_kg"] > 0
    assert kpis.vehicles_observed > 20 and kpis.co2_kg > 0


def test_lust_state_needs_repair_and_reloads(lust_run):
    facts, col, obs, kpis, state, n_fixed = lust_run
    assert n_fixed == 201, "SUMO 1.27.1 writes state=\"\" for each actuated TLS"
    with SumoConnection(SumoConfig(load_state=state, label="lust_reload")) as api:
        assert api.simulation.getTime() == facts["time"]
        assert api.vehicle.getIDCount() == facts["running"]
        sim = SimulationController(api)
        sim.step()
        assert sim.time == facts["time"] + 1


def test_lust_bus_patterns_for_headway():
    """Headways are keyed per stop pattern: 2 patterns per line, all planned every 1 800 s."""
    bus_files = [f for f in cfg_route_files(DEFAULT_SUMOCFG) if "bus" in f.name.lower()]
    plan = load_bus_plan(bus_files)
    assert len({t.pattern for t in plan.values()}) == 76
    assert {t.planned_headway for t in plan.values()} == {1800.0}
