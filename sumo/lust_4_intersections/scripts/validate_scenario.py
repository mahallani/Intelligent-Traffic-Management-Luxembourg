"""
Validation of the reduced Kirchberg 4-signal scenario (mandatory tests + S0..S3 feasibility).

Every check is EXECUTED; the report says PASS / FAIL with the measured values.

Usage (PowerShell, project root):
    python sumo\\lust_4_intersections\\scripts\\validate_scenario.py
    python sumo\\lust_4_intersections\\scripts\\validate_scenario.py --congested-scale 5

Outputs: sumo\\lust_4_intersections\\output\\validation_report.json and .md
Exit code 0 if all mandatory tests pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import sumolib  # noqa: E402
import traci  # noqa: E402

from traci_layer import CollectorConfig, SumoConfig, SumoConnection, TrafficDataCollector  # noqa: E402
from traci_layer.config import find_sumo_binary  # noqa: E402

CFG = HERE / "kirchberg_4tls.sumocfg"
NET = HERE / "net" / "kirchberg_4tls.net.xml"
ROUTES = HERE / "routes" / "kirchberg_0700_0800.rou.xml"
STOPS = HERE / "additional" / "busstops_kirchberg.add.xml"
REF = HERE / "net" / "tls_reference_from_lust.json"
OUT = HERE / "output"
EXPECTED_TLS = ["-20484", "-23354", "-28692", "-29958"]
AVENUE_EAST = ["--31070#8", "--31070#7", "--31070#6", "--31070#5", "--31070#4"]

results: list[dict] = []


def record(name: str, passed: bool, **details) -> bool:
    results.append({"test": name, "passed": bool(passed), **details})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}  {json.dumps(details, default=str)[:300]}", flush=True)
    return passed


def sumo_cfg(label: str, scale: float = 1.0, extra: list[str] | None = None) -> SumoConfig:
    args = ["--scale", str(scale)] + (extra or [])  # SumoConfig(quiet=True) already silences warnings
    return SumoConfig(sumocfg=CFG, label=label, output_dir=OUT / "runs" / label, extra_args=args)


def collector(api, name: str) -> TrafficDataCollector:
    cc = CollectorConfig(snapshot_interval=300, lane_scope="tls", bus_route_files=[ROUTES])
    return TrafficDataCollector(api, cc, sumocfg=CFG, scenario=name, run_id=name)


def kpi_summary(k) -> dict:
    return {"vehicles": k.vehicles_observed, "completed_trips": k.completed_trips,
            "avg_travel_time_s": round(k.average_travel_time_s or 0, 1),
            "total_waiting_time_s": round(k.total_waiting_time_s, 0),
            "avg_waiting_per_vehicle_s": round(k.average_waiting_time_per_vehicle_s or 0, 1),
            "mean_speed_kmh": round(k.network_mean_speed_kmh or 0, 1),
            "avg_total_queue_m": round(k.average_total_queue_length_m or 0, 1),
            "max_lane_queue_m": round(k.max_lane_queue_length_m or 0, 1),
            "time_loss_s": round(k.total_time_loss_in_window_s, 0), "co2_kg": round(k.co2_kg, 1),
            "teleports": k.teleports, "pending_end": k.pending_vehicles_end,
            "emergency_travel_time_s": k.emergency_average_travel_time_s}


# ============================================================ mandatory tests
def t1_network_loads():
    proc = subprocess.run([find_sumo_binary(), "-n", str(NET), "--end", "1", "--no-step-log", "true"],
                          capture_output=True, text=True)
    net = sumolib.net.readNet(str(NET), withPrograms=True)
    record("T1 network loads in SUMO", proc.returncode == 0 and "Error" not in proc.stderr,
           sumo_version=subprocess.run([find_sumo_binary(), "--version"], capture_output=True, text=True).stdout.splitlines()[0],
           edges=len(net.getEdges()), nodes=len(net.getNodes()), stderr=proc.stderr.strip()[:200])
    return net


def t2_traffic_lights(net):
    ids = sorted(t.getID() for t in net.getTrafficLights())
    ref = json.loads(REF.read_text())
    identical = {}
    for t in net.getTrafficLights():
        prog = list(t.getPrograms().values())[0]
        phases = [[p.state, p.duration] for p in prog.getPhases()]
        links = sorted([c[0].getID(), c[1].getID(), c[2]] for c in t.getConnections())
        identical[t.getID()] = phases == ref[t.getID()]["phases"] and links == ref[t.getID()]["links"]
    record("T2 exactly 4 traffic lights, LuST programs preserved", ids == EXPECTED_TLS and all(identical.values()),
           tls_ids=ids, identical_to_lust=identical)


def t3_routes_and_connections(net):
    root = ET.parse(ROUTES).getroot()
    bad, n, nedges = [], 0, 0
    for v in root.iter("vehicle"):
        edges = v.find("route").get("edges").split()
        n += 1
        nedges += len(edges)
        for a, b in zip(edges, edges[1:]):
            if not net.hasEdge(a) or not net.hasEdge(b) or not net.getEdge(a).getConnections(net.getEdge(b)):
                bad.append((v.get("id"), a, b))
    stop_lanes = [s.get("lane") for s in ET.parse(STOPS).getroot().iter("busStop")]
    lanes_ok = all(net.hasEdge(l.rsplit("_", 1)[0]) for l in stop_lanes)
    record("T3 all routes connected, bus stops on existing lanes", not bad and lanes_ok,
           vehicles=n, avg_route_edges=round(nedges / n, 1), broken_links=bad[:5], bus_stops=len(stop_lanes))


def t4_to_t8_baseline(scale: float, label: str) -> dict:
    """Full 07:00-08:00 run with TraCI: progress, vehicles per signal, buses, KPIs."""
    stop_file = OUT / "runs" / label / "stops.xml"
    t0 = time.perf_counter()
    seen_at_tls: dict[str, set] = {t: set() for t in EXPECTED_TLS}
    with SumoConnection(sumo_cfg(label, scale, ["--stop-output", str(stop_file)])) as api:
        col = collector(api, label)
        for _ in col.run(until=28800, observe_every=300, stop_when_empty=False):
            pass
        end_t = api.simulation.getTime()
        kpis = col.kpis()
        stats = {"departed": col.sim.counters.departed, "arrived": col.sim.counters.arrived,
                 "teleports": col.sim.counters.teleports, "collisions": col.sim.counters.collisions}
        bus_events = col.buses.events
    # vehicles through each signal: second light run sampling the controlled lanes every 5 s
    with SumoConnection(sumo_cfg(label + "_count", scale)) as api:
        lane_ids = {t: set(api.trafficlight.getControlledLanes(t)) for t in EXPECTED_TLS}
        while api.simulation.getTime() < 28800:
            api.simulationStep()
            if int(api.simulation.getTime()) % 5 == 0:
                for t, ls in lane_ids.items():
                    for l in ls:
                        seen_at_tls[t].update(api.lane.getLastStepVehicleIDs(l))
    wall = time.perf_counter() - t0
    record("T4 simulation starts and progresses without error", end_t == 28800 and stats["collisions"] == 0,
           end_time=end_t, wall_clock_s=round(wall, 1), **stats)
    per_tls = {t: len(v) for t, v in seen_at_tls.items()}
    record("T5 vehicles actually drive through each of the 4 intersections", all(n > 0 for n in per_tls.values())
           and stats["arrived"] > 0, vehicles_per_signal=per_tls)
    truth = list(ET.parse(stop_file).getroot().iter("stopinfo"))
    stops_served = sorted({s.get("busStop") for s in truth})
    buses = sorted({s.get("id") for s in truth})
    lines = sorted({b.rsplit("_", 1)[0] for b in buses})
    record("T6 buses run and serve the bus stops", len(buses) > 0 and len(bus_events) == len(truth),
           buses=len(buses), lines=lines, stop_events_sumo=len(truth), stop_events_traci_layer=len(bus_events),
           stops_served=stops_served, mean_dwell_s=round(sum(float(s.get("ended")) - float(s.get("started"))
                                                            for s in truth) / max(len(truth), 1), 1))
    record("T8 KPIs measured (waiting, travel time, speed, queues)",
           kpis.average_travel_time_s is not None and kpis.average_total_queue_length_m is not None,
           scale=scale, **kpi_summary(kpis))
    return kpi_summary(kpis)


def t7_traffic_light_control():
    with SumoConnection(sumo_cfg("tlscontrol")) as api:
        for _ in range(10):
            api.simulationStep()
        tl = api.trafficlight
        checks = {}
        for t in EXPECTED_TLS:
            read = (tl.getRedYellowGreenState(t), tl.getPhase(t), tl.getProgram(t), tl.getNextSwitch(t))
            n_ph = len(tl.getAllProgramLogics(t)[0].phases)
            tl.setPhase(t, n_ph - 1)
            ok_phase = tl.getPhase(t) == n_ph - 1
            tl.setPhaseDuration(t, 25)
            ok_dur = abs(tl.getNextSwitch(t) - api.simulation.getTime() - 25) < 1e-6
            state = "G" * len(read[0])
            tl.setRedYellowGreenState(t, state)
            api.simulationStep()
            ok_state = tl.getRedYellowGreenState(t) == state
            tl.setProgram(t, "0")
            ok_restore = tl.getProgram(t) == "0"
            logic = tl.getAllProgramLogics(t)[0]
            logic.programID = "S1_test"
            logic.phases = tuple(traci.trafficlight.Phase(p.duration + 5, p.state) for p in logic.phases)
            tl.setProgramLogic(t, logic)
            ok_logic = tl.getProgram(t) == "S1_test"
            tl.setProgram(t, "0")
            checks[t] = {"read_state": read[0], "setPhase": ok_phase, "setPhaseDuration": ok_dur,
                         "setRedYellowGreenState": ok_state, "setProgram": ok_restore, "setProgramLogic": ok_logic}
    record("T7 traffic lights readable and controllable with TraCI",
           all(all(v for k, v in c.items() if k != "read_state") for c in checks.values()), per_signal=checks)


# ======================================================== strategy feasibility
def avenue_green_plan(api, factor: float = 1.5):
    """S1 example: lengthen the green phases serving the avenue (illustrative strategy)."""
    tl = api.trafficlight
    for t in EXPECTED_TLS:
        links = tl.getControlledLinks(t)
        avenue_idx = [i for i, g in enumerate(links) if g and "31070" in g[0][0]]
        logic = tl.getAllProgramLogics(t)[0]
        phases = []
        for p in logic.phases:
            serves_avenue = any(p.state[i] == "G" for i in avenue_idx)
            phases.append(traci.trafficlight.Phase(round(p.duration * factor) if serves_avenue and "y" not in p.state
                                                   else p.duration, p.state))
        logic.programID, logic.phases = "S1_avenue_green", tuple(phases)
        tl.setProgramLogic(t, logic)


def run_strategy(name: str, scale: float, setup=None, on_step=None, ev_type: str | None = None) -> dict:
    with SumoConnection(sumo_cfg(name, scale)) as api:
        if ev_type:
            api.route.add("ev_route", AVENUE_EAST)
            api.vehicle.add("ambulance", "ev_route", typeID=ev_type, depart="26400", departLane="best",
                            departSpeed="max")
        if setup:
            setup(api)
        col = collector(api, name)
        for _ in col.run(until=28800, observe_every=300, stop_when_empty=False,
                         on_step=(lambda c: on_step(api)) if on_step else None):
            pass
        out = kpi_summary(col.kpis())
        out["extra"] = getattr(api, "_extra", None)
    return out


def emergency_preemption(api, horizon_m: float = 150.0):
    """S3 example: give green to the ambulance's link at its next signal (no yellow transition)."""
    if "ambulance" not in api.vehicle.getIDList():
        return
    nxt = api.vehicle.getNextTLS("ambulance")
    if not nxt:
        return
    tls, link, dist, state = nxt[0]
    if dist > horizon_m:
        return
    tl = api.trafficlight
    if state in "Gg":
        remaining = tl.getNextSwitch(tls) - api.simulation.getTime()
        if remaining < 5:
            tl.setPhaseDuration(tls, 5)
        return
    logic = next(lg for lg in tl.getAllProgramLogics(tls) if lg.programID == tl.getProgram(tls))
    target = next((i for i, p in enumerate(logic.phases) if p.state[link] == "G"), None)
    if target is not None:
        tl.setPhase(tls, target)
        api._extra = (api._extra or 0) + 1 if hasattr(api, "_extra") else 1


def incident_reroute_factory(reroute: bool):
    """S2 example: lane closure + slowdown on --31070#6 from 07:15 to 07:35; optional rerouting."""
    state = {"rerouted": 0, "changed": 0}

    def on_step(api):
        t = api.simulation.getTime()
        if t == 26100:
            api.lane.setDisallowed("--31070#6_1", ["passenger", "bus", "emergency"])
            api.lane.setMaxSpeed("--31070#6_0", 2.0)
        if t == 27300:
            api.lane.setAllowed("--31070#6_1", ["all"])
            api.lane.setMaxSpeed("--31070#6_0", api.lane.getMaxSpeed("--31070#6_1"))
        if reroute and 26100 <= t < 27300 and int(t) % 30 == 0:
            api.edge.adaptTraveltime("--31070#6", 600.0, 26100, 27300)
            for vid in api.vehicle.getIDList():
                route = api.vehicle.getRoute(vid)
                idx = api.vehicle.getRouteIndex(vid)
                if "--31070#6" in route[idx + 1:] and api.vehicle.getVehicleClass(vid) != "bus":
                    api.vehicle.rerouteTraveltime(vid, currentTravelTimes=False)
                    state["rerouted"] += 1
                    if "--31070#6" not in api.vehicle.getRoute(vid)[idx + 1:]:
                        state["changed"] += 1
        api._extra = dict(state)
    return on_step


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--congested-scale", type=float, default=5.0, help="demand factor for congestion tests")
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    print("=" * 60, "\nKIRCHBERG 4-SIGNAL SCENARIO - VALIDATION\n" + "=" * 60)
    net = t1_network_loads()
    t2_traffic_lights(net)
    t3_routes_and_connections(net)
    base = t4_to_t8_baseline(1.0, "baseline_x1")
    t7_traffic_light_control()

    s = args.congested_scale
    print(f"\n--- Strategy feasibility (demand x{s}) ---")
    s0 = run_strategy("S0_do_nothing", s, ev_type="emergency_plain")
    s1 = run_strategy("S1_signal_plan", s, setup=avenue_green_plan, ev_type="emergency_plain")
    s2a = run_strategy("S2_incident_no_reroute", s, on_step=incident_reroute_factory(False))
    s2b = run_strategy("S2_incident_reroute", s, on_step=incident_reroute_factory(True))
    s3 = run_strategy("S3_emergency_priority", s, on_step=emergency_preemption, ev_type="emergency_plain")
    record("S0 do-nothing baseline runs", s0["vehicles"] > 0, **s0)
    record("S1 signal strategy changes the outcome", s1["total_waiting_time_s"] != s0["total_waiting_time_s"],
           waiting_S0=s0["total_waiting_time_s"], waiting_S1=s1["total_waiting_time_s"],
           travel_S0=s0["avg_travel_time_s"], travel_S1=s1["avg_travel_time_s"])
    record("S2 rerouting possible (alternative routes exist)", (s2b["extra"] or {}).get("changed", 0) > 0,
           reroute_calls=(s2b["extra"] or {}).get("rerouted"), routes_changed=(s2b["extra"] or {}).get("changed"),
           waiting_incident_no_reroute=s2a["total_waiting_time_s"], waiting_incident_reroute=s2b["total_waiting_time_s"],
           travel_no_reroute=s2a["avg_travel_time_s"], travel_reroute=s2b["avg_travel_time_s"])
    record("S3 emergency vehicle priority feasible",
           s3["emergency_travel_time_s"] is not None and s0["emergency_travel_time_s"] is not None,
           ambulance_travel_S0_s=s0["emergency_travel_time_s"], ambulance_travel_S3_s=s3["emergency_travel_time_s"],
           preemptions=s3["extra"], total_waiting_S0=s0["total_waiting_time_s"], total_waiting_S3=s3["total_waiting_time_s"])

    mandatory = [r for r in results if r["test"].startswith("T")]
    ok = all(r["passed"] for r in results)
    (OUT / "validation_report.json").write_text(json.dumps(
        {"all_passed": ok, "baseline_x1": base, "congested_scale": s,
         "strategies": {"S0": s0, "S1": s1, "S2_no_reroute": s2a, "S2_reroute": s2b, "S3": s3},
         "tests": results}, indent=1, default=str))
    lines = ["# Validation report - Kirchberg 4 signals", "", "| Test | Result |", "|---|---|"]
    lines += [f"| {r['test']} | {'PASS' if r['passed'] else 'FAIL'} |" for r in results]
    (OUT / "validation_report.md").write_text("\n".join(lines) + "\n")
    print(f"\n{sum(r['passed'] for r in results)}/{len(results)} checks passed "
          f"({sum(r['passed'] for r in mandatory)}/{len(mandatory)} mandatory) -> {OUT / 'validation_report.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
