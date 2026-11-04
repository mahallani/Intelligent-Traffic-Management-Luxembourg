"""
TEMPLATE for the Intervention -> Decision loop: run several strategies from the SAME
saved state, with the SAME emergency mission, and compare the SAME KPIs.

The two strategies used here are only placeholders so that the mechanics can be tested:

* S0_do_nothing    : LuST signal programs as loaded (program "0")
* S3_lust_static   : the alternative static plans shipped with LuST in tll.static.xml
                     (program "1"). This is NOT our S3 optimisation, just an existing
                     alternative plan used to exercise the pipeline.

WARNING (verified): loading tll.static.xml as an additional file makes program "1" the
ACTIVE program of all 201 signals, even when a saved state is loaded. It must therefore
only be loaded by the strategy that uses it - never by the S0 baseline.

The real S1..S4 logic belongs to the Intervention Agent (it receives the
TrafficLightActuator and is called at every step through ``on_step``).

Usage (project root):
    python scripts/example_compare_scenarios.py --state data/states/lust_0700.xml.gz --duration 900
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from traci_layer import (DEFAULT_OUTPUT_DIR, EMERGENCY_VTYPES_FILE, LUST_SCENARIO_DIR, CollectorConfig,  # noqa: E402
                         EmergencyVehicleSpec, SumoConfig, SumoConnection, TrafficDataCollector,
                         TrafficLightActuator, compare_scenarios, format_kpis, spawn_emergency_vehicle, write_json)


def strategy_do_nothing(api, actuator):
    assert set(api.trafficlight.getProgram(t) for t in api.trafficlight.getIDList()) == {"0"}


def strategy_lust_static_plans(api, actuator):
    for tls in api.trafficlight.getIDList():
        if api.trafficlight.getProgram(tls) != "1":
            actuator.set_program(tls, "1")


#: name -> (extra additional files, setup function applied at incident time)
STRATEGIES = {
    "S0_do_nothing": ([], strategy_do_nothing),
    "S3_lust_static": ([LUST_SCENARIO_DIR / "tll.static.xml"], strategy_lust_static_plans),
}


def run_strategy(name, extra_files, setup, args):
    cfg = SumoConfig(load_state=args.state, use_libsumo=args.libsumo, label=name,
                     output_dir=args.out / "sumo_outputs" / name,
                     additional_files=[EMERGENCY_VTYPES_FILE, *extra_files])
    with SumoConnection(cfg) as api:
        t0 = api.simulation.getTime()
        spawn_emergency_vehicle(api, EmergencyVehicleSpec("emergency_1", args.ev_from, args.ev_to,
                                                          depart=t0 + 30))
        actuator = TrafficLightActuator(api)
        setup(api, actuator)                      # apply the strategy at incident time
        col = TrafficDataCollector(api, CollectorConfig(snapshot_interval=120, lane_scope="tls"),
                                   scenario=name, run_id=name)
        for _ in col.run(duration=args.duration, observe_every=120):
            pass
        kpis = col.kpis()
        print(format_kpis(kpis), flush=True)
        return kpis


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, default=PROJECT_ROOT / "data" / "states" / "lust_0700.xml.gz")
    p.add_argument("--duration", type=float, default=900)
    p.add_argument("--ev-from", default="-31952#8")
    p.add_argument("--ev-to", default="--31272#3")
    p.add_argument("--libsumo", action="store_true")
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR / "comparison")
    args = p.parse_args()
    if not args.state.exists():
        sys.exit(f"State {args.state} not found. Create it with:\n"
                 f"  python -m traci_layer --start-at 25200 --duration 0 --save-state {args.state} --no-export")
    results = {name: run_strategy(name, files, setup, args) for name, (files, setup) in STRATEGIES.items()}
    table = compare_scenarios(results)
    print(table.to_string(float_format=lambda v: f"{v:,.2f}"))
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "kpi_comparison.csv")
    write_json({k: v for k, v in results.items()}, args.out / "kpis_by_scenario.json")
    print(f"\nSaved: {args.out / 'kpi_comparison.csv'}")


if __name__ == "__main__":
    main()
