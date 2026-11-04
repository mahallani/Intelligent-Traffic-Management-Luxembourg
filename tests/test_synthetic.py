"""
Validation of the collection layer against SUMO's own ground truth.

A small 3x3 signalised grid is simulated to completion. Our values (travel time,
waiting time, distance, time loss, emissions) are compared with SUMO's tripinfo output
written with the emissions device - i.e. what SUMO itself computes for each trip.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from traci_layer import (EMERGENCY_VTYPES_FILE, CollectorConfig, EmergencyVehicleSpec, RunExporter, SumoConfig,
                         SumoConnection, TrafficDataCollector, TrafficLightActuator, observations_to_dataframe,
                         read_jsonl, spawn_emergency_vehicle)
from traci_layer.readers import is_libsumo


def _run(cfg_path, tmp_path, label, libsumo=False, details=True, exporter=None):
    out = tmp_path / f"out_{label}"
    sc = SumoConfig(sumocfg=cfg_path, output_dir=out, emission_device=True,
                    additional_files=[EMERGENCY_VTYPES_FILE], label=label, use_libsumo=libsumo,
                    extra_args=["--stop-output", str(out / "stops.xml")])
    cc = CollectorConfig(snapshot_interval=30, include_details=details,
                         bus_route_files=[cfg_path.parent / "grid.rou.xml"])
    with SumoConnection(sc) as api:
        spawn_emergency_vehicle(api, EmergencyVehicleSpec("ambulance", "A2B2", "C0B0", depart=40))
        col = TrafficDataCollector(api, cc, sumocfg=cfg_path, scenario="TEST", run_id=label)
        obs = []
        for o in col.run(until=2000, observe_every=30):
            obs.append(o)
            if exporter:
                exporter.write_observation(o)
        files = exporter.finalize(col) if exporter else None
        kpis = col.kpis()
        backend = is_libsumo(api)
    tripinfo = {t.get("id"): t for t in ET.parse(out / "tripinfo.xml").getroot().iter("tripinfo")}
    col.sumo_stops = list(ET.parse(out / "stops.xml").getroot().iter("stopinfo"))  # SUMO ground truth
    return col, obs, kpis, tripinfo, files, backend


@pytest.fixture(scope="module")
def traci_run(synthetic_scenario, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run")
    exporter = RunExporter(tmp / "export", "synthetic")
    return _run(synthetic_scenario, tmp, "traci", exporter=exporter)


def test_all_trips_recorded(traci_run):
    col, obs, kpis, tripinfo, _, _ = traci_run
    ours = {t.vehicle_id: t for t in col.vehicles.completed}
    assert set(ours) == set(tripinfo)
    assert kpis.completed_trips == len(tripinfo) > 100


def test_travel_time_matches_sumo_exactly(traci_run):
    col, *_ , tripinfo, _, _ = traci_run
    for t in col.vehicles.completed:
        assert t.travel_time == pytest.approx(float(tripinfo[t.vehicle_id].get("duration")), abs=1e-6)


def test_waiting_time_matches_sumo(traci_run):
    col, *_ , tripinfo, _, _ = traci_run
    diffs = [abs(t.waiting_time - float(tripinfo[t.vehicle_id].get("waitingTime"))) for t in col.vehicles.completed]
    assert max(diffs) <= 1.0  # at most one step


def test_time_loss_and_distance_close_to_sumo(traci_run):
    col, *_ , tripinfo, _, _ = traci_run
    for t in col.vehicles.completed:
        ti = tripinfo[t.vehicle_id]
        assert t.time_loss == pytest.approx(float(ti.get("timeLoss")), abs=3.0)
        # we integrate speed*dt; the last step before arrival is not observed
        assert t.route_length == pytest.approx(float(ti.get("routeLength")), rel=0.05, abs=30.0)


def test_emissions_match_sumo_emission_device(traci_run):
    col, *_ , tripinfo, _, _ = traci_run
    ours = sum(t.co2_mg for t in col.vehicles.completed)
    sumo = sum(float(ti.find("emissions").get("CO2_abs")) for ti in tripinfo.values())
    assert ours == pytest.approx(sumo, rel=0.02)
    ours_nox = sum(t.nox_mg for t in col.vehicles.completed)
    sumo_nox = sum(float(ti.find("emissions").get("NOx_abs")) for ti in tripinfo.values())
    assert ours_nox == pytest.approx(sumo_nox, rel=0.02)
    ours_fuel = sum(t.fuel_mg for t in col.vehicles.completed)
    sumo_fuel = sum(float(ti.find("emissions").get("fuel_abs")) for ti in tripinfo.values())
    assert ours_fuel == pytest.approx(sumo_fuel, rel=0.02)


def test_network_emission_total_equals_sum_of_trips(traci_run):
    col, _, kpis, *_ = traci_run
    assert kpis.co2_kg * 1e6 == pytest.approx(sum(t.co2_mg for t in col.vehicles.completed), rel=1e-6)


def test_bus_stop_events(traci_run):
    col, *_ = traci_run
    events = col.buses.events
    assert [e.vehicle_id for e in events] == ["L1_0", "L1_1"]
    assert all(e.stop_id == "stopB" and e.line == "L1" for e in events)
    assert events[1].planned_headway == 60          # planned departures 10 s and 70 s
    # compare with SUMO's own stop-output (ground truth)
    truth = {s.get("id"): s for s in col.sumo_stops}
    for e in events:
        assert e.arrival == pytest.approx(float(truth[e.vehicle_id].get("started")), abs=1.0)
        assert e.departure == pytest.approx(float(truth[e.vehicle_id].get("ended")), abs=1.0)
        assert e.dwell == pytest.approx(20, abs=1)
    sumo_headway = float(truth["L1_1"].get("started")) - float(truth["L1_0"].get("started"))
    assert events[1].headway == pytest.approx(sumo_headway, abs=1.0)


def test_emergency_vehicle_tracked(traci_run):
    col, _, kpis, tripinfo, _, _ = traci_run
    assert kpis.emergency_missions == kpis.emergency_completed == 1
    rec = col.emergency.completed[0]
    assert rec.vehicle_id == "ambulance"
    assert rec.travel_time_s == pytest.approx(float(tripinfo["ambulance"].get("duration")))
    assert rec.free_flow_time_s > 0
    assert rec.delay_s == pytest.approx(rec.travel_time_s - rec.free_flow_time_s)
    assert col.vehicles.completed and any(t.vclass == "emergency" for t in col.vehicles.completed)


def test_observation_structure(traci_run):
    _, obs, *_ = traci_run
    o = obs[2]
    for key in ("meta", "simulation", "vehicles", "congestion", "travel", "environment", "buses",
                "emergency", "traffic_lights"):
        assert key in o
    assert o["traffic_lights"]["total_signals"] > 0
    assert 0 <= o["congestion"]["average_occupancy_pct"] <= 100
    assert o["congestion"]["queue_method"] == "tls_lanes_vehicle_positions"


def test_export_files(traci_run):
    col, obs, _, _, files, _ = traci_run
    for name in ("observations_jsonl", "observations_summary_csv", "edges", "lanes", "traffic_lights",
                 "vehicles", "trips", "bus_stop_events", "kpis"):
        assert name in files and files[name].exists(), name
    back = read_jsonl(files["observations_jsonl"])
    assert len(back) == len(obs)
    df = observations_to_dataframe(back)
    assert len(df) == len(obs) and "vehicles.count" in df.columns


def test_libsumo_gives_identical_results(synthetic_scenario, tmp_path, traci_run):
    pytest.importorskip("libsumo")
    col_t, _, k_t, *_ = traci_run
    col_l, _, k_l, _, _, backend = _run(synthetic_scenario, tmp_path, "libsumo", libsumo=True, details=False)
    assert backend is True
    assert k_l.completed_trips == k_t.completed_trips
    assert k_l.total_waiting_time_s == pytest.approx(k_t.total_waiting_time_s)
    assert k_l.co2_kg == pytest.approx(k_t.co2_kg, rel=1e-9)


def test_traffic_light_actuators(synthetic_scenario, tmp_path):
    with SumoConnection(SumoConfig(sumocfg=synthetic_scenario, label="act")) as api:
        for _ in range(5):
            api.simulationStep()
        act = TrafficLightActuator(api)
        tls = max(api.trafficlight.getIDList(),
                  key=lambda t: len(api.trafficlight.getAllProgramLogics(t)[0].phases))
        assert len(api.trafficlight.getAllProgramLogics(tls)[0].phases) >= 4
        act.set_phase(tls, 2)
        assert api.trafficlight.getPhase(tls) == 2
        act.set_phase_duration(tls, 42)
        assert api.trafficlight.getNextSwitch(tls) - api.simulation.getTime() == pytest.approx(42)
        lane = api.trafficlight.getControlledLanes(tls)[0]
        served = act.phases_serving_lane(tls, lane)
        assert served, "every controlled lane gets green in some phase"
        act.set_phase(tls, served[0])
        assert act.extend_green(tls, lane, 10) is True
        act.set_program(tls, "off")
        assert api.trafficlight.getProgram(tls) == "off"
        act.restore(tls)
        assert api.trafficlight.getProgram(tls) == "0"
        assert [r.action for r in act.log][:3] == ["set_phase", "set_phase_duration", "set_phase"]


def test_state_save_and_reload(synthetic_scenario, tmp_path):
    from traci_layer.simulation import SimulationController

    state = tmp_path / "state.xml.gz"
    with SumoConnection(SumoConfig(sumocfg=synthetic_scenario, label="save")) as api:
        sim = SimulationController(api)
        for _ in range(60):
            sim.step()
        n_before = api.vehicle.getIDCount()
        sim.save_state(state)
    with SumoConnection(SumoConfig(sumocfg=synthetic_scenario, load_state=state, label="load")) as api:
        assert api.simulation.getTime() == 60
        assert api.vehicle.getIDCount() == n_before
        col = TrafficDataCollector(api, CollectorConfig(bus_route_files=[]), sumocfg=synthetic_scenario)
        assert len(col.vehicles.active) == n_before
        assert all(not r.observed_from_departure for r in col.vehicles.active.values())


def test_light_step_vars_preset(synthetic_scenario, tmp_path, traci_run):
    """The faster 'light' preset keeps travel/waiting/CO2 identical (only CO/HC/PMx are dropped)."""
    _, _, k_std, *_ = traci_run
    sc = SumoConfig(sumocfg=synthetic_scenario, additional_files=[EMERGENCY_VTYPES_FILE], label="light")
    cc = CollectorConfig(snapshot_interval=30, light_step_vars=True,
                         bus_route_files=[synthetic_scenario.parent / "grid.rou.xml"])
    with SumoConnection(sc) as api:
        spawn_emergency_vehicle(api, EmergencyVehicleSpec("ambulance", "A2B2", "C0B0", depart=40))
        col = TrafficDataCollector(api, cc, sumocfg=synthetic_scenario)
        list(col.run(until=2000, observe_every=30))
        k = col.kpis()
    assert k.completed_trips == k_std.completed_trips
    assert k.total_waiting_time_s == pytest.approx(k_std.total_waiting_time_s)
    assert k.co2_kg == pytest.approx(k_std.co2_kg)
    assert k.pmx_g is None  # not integrated in light mode -> never reported as 0


# ---------------------------------------------------------------- regression tests (code review)
def test_observation_windows_do_not_double_count(traci_run):
    _, obs, *_ = traci_run
    per_window = sum(o["travel"]["since_last_observation"]["completed_trips"] for o in obs)
    assert per_window == obs[-1]["travel"]["cumulative"]["completed_trips"]


def test_emergency_delay_consistent_with_sumo_time_loss(traci_run):
    col, *_ , tripinfo, _, _ = traci_run
    rec = col.emergency.completed[0]
    # free-flow time now includes junction internal lanes -> delay ~ SUMO's own timeLoss
    assert rec.delay_s == pytest.approx(float(tripinfo["ambulance"].get("timeLoss")), abs=5.0)
    assert rec.route_length_m == pytest.approx(float(tripinfo["ambulance"].get("routeLength")), rel=0.05)
    assert rec.mission_time_s == pytest.approx(rec.travel_time_s + rec.depart_delay_s)


def test_extend_green_never_shortens(synthetic_scenario):
    with SumoConnection(SumoConfig(sumocfg=synthetic_scenario, label="ext")) as api:
        api.simulationStep()
        act = TrafficLightActuator(api)
        tls = max(api.trafficlight.getIDList(),
                  key=lambda t: len(api.trafficlight.getAllProgramLogics(t)[0].phases))
        lane = api.trafficlight.getControlledLanes(tls)[0]
        act.set_phase(tls, act.phases_serving_lane(tls, lane)[0])
        act.set_phase_duration(tls, 70)
        before = api.trafficlight.getNextSwitch(tls)
        assert act.extend_green(tls, lane, extra_s=10, max_remaining_s=60) is False
        assert api.trafficlight.getNextSwitch(tls) == before
        assert act.extend_green(tls, lane, extra_s=10, max_remaining_s=120) is True
        assert api.trafficlight.getNextSwitch(tls) == pytest.approx(before + 10)


def test_bus_already_running_when_collector_starts(synthetic_scenario, tmp_path):
    out = tmp_path / "late"
    sc = SumoConfig(sumocfg=synthetic_scenario, label="late", output_dir=out,
                    extra_args=["--stop-output", str(out / "stops.xml")])
    with SumoConnection(sc) as api:
        for _ in range(75):
            api.simulationStep()
        col = TrafficDataCollector(api, CollectorConfig(bus_route_files=[synthetic_scenario.parent / "grid.rou.xml"]),
                                   sumocfg=synthetic_scenario)
        bus = col.buses.active.get("L1_0")
        list(col.run(until=2000, observe_every=60))
    truth = {s.get("id"): s for s in ET.parse(out / "stops.xml").getroot().iter("stopinfo")}
    started, ended = float(truth["L1_0"].get("started")), float(truth["L1_0"].get("ended"))
    if bus is not None:  # still on the network at t=75
        if ended <= 75:
            assert bus.stops_done == 1 and bus.at_stop is None
        elif started <= 75:
            assert bus.at_stop == "stopB"
    # never a stop event with an invented arrival time for L1_0
    assert all(e.arrival >= 75 for e in col.buses.events)
    assert [e.vehicle_id for e in col.buses.events if e.vehicle_id == "L1_0"] == ([] if started <= 75 else ["L1_0"])
