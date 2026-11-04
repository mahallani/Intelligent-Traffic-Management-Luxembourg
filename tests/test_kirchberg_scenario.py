"""
Fast tests of the reduced Kirchberg 4-signal scenario (sumo/lust_4_intersections).
They only need the scenario folder (not the full LuST). Full validation incl. S0..S3:
    python sumo/lust_4_intersections/scripts/validate_scenario.py
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest
import sumolib

from conftest import PROJECT_ROOT
from traci_layer import CollectorConfig, SumoConfig, SumoConnection, TrafficDataCollector

SC = PROJECT_ROOT / "sumo" / "lust_4_intersections"
CFG = SC / "kirchberg_4tls.sumocfg"
NET = SC / "net" / "kirchberg_4tls.net.xml"
ROUTES = SC / "routes" / "kirchberg_0700_0800.rou.xml"
TLS = ["-20484", "-23354", "-28692", "-29958"]


@pytest.fixture(scope="module")
def net():
    return sumolib.net.readNet(str(NET), withPrograms=True)


def test_exactly_four_signals_with_lust_programs(net):
    ref = json.loads((SC / "net" / "tls_reference_from_lust.json").read_text())
    assert sorted(t.getID() for t in net.getTrafficLights()) == TLS
    for t in net.getTrafficLights():
        prog = list(t.getPrograms().values())[0]
        assert [[p.state, p.duration] for p in prog.getPhases()] == ref[t.getID()]["phases"]


def test_routes_are_connected(net):
    for v in ET.parse(ROUTES).getroot().iter("vehicle"):
        edges = v.find("route").get("edges").split()
        for a, b in zip(edges, edges[1:]):
            assert net.getEdge(a).getConnections(net.getEdge(b)), (v.get("id"), a, b)


def test_one_hour_run_with_buses_and_kpis():
    cfg = SumoConfig(sumocfg=CFG, label="kirch_test", output_dir=SC / "output" / "pytest")
    with SumoConnection(cfg) as api:
        assert sorted(api.trafficlight.getIDList()) == TLS
        col = TrafficDataCollector(api, CollectorConfig(snapshot_interval=900, bus_route_files=[ROUTES]), sumocfg=CFG)
        obs = list(col.run(until=28800, observe_every=900, stop_when_empty=False))
        k = col.kpis()
    assert len(obs) == 4
    assert k.vehicles_observed == 778 and k.completed_trips > 700 and k.teleports == 0
    assert k.average_travel_time_s and k.average_total_queue_length_m is not None
    assert len(col.buses.events) > 0 and k.bus_trips_observed == 19


def test_signals_controllable():
    with SumoConnection(SumoConfig(sumocfg=CFG, label="kirch_ctl")) as api:
        api.simulationStep()
        for t in TLS:
            api.trafficlight.setPhase(t, 1)
            assert api.trafficlight.getPhase(t) == 1
            api.trafficlight.setPhaseDuration(t, 30)
            assert api.trafficlight.getNextSwitch(t) - api.simulation.getTime() == pytest.approx(30)
