"""
Command line runner:  python -m traci_layer [options]

Examples (from the project root, Windows PowerShell or Linux):

    # 5 minutes at the start of the LuST day, one report per minute
    python -m traci_layer --duration 300 --interval 60

    # morning peak: fast-forward to 07:00 without collection, observe 10 min, export
    python -m traci_layer --start-at 25200 --duration 600 --interval 120 --details

    # same thing + an ambulance mission + save the 07:00 state for scenario runs
    python -m traci_layer --start-at 25200 --duration 900 --save-state data/states/lust_0700.xml.gz \
        --emergency-from=-31608#3 --emergency-to=-32922#2 --emergency-at 25260
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .collector import TrafficDataCollector, clock
from .config import DEFAULT_OUTPUT_DIR, DEFAULT_SUMOCFG, EMERGENCY_VTYPES_FILE, CollectorConfig, SumoConfig
from .connection import SumoConnection
from .emergency_data import EmergencyVehicleSpec, spawn_emergency_vehicle
from .export import RunExporter
from .report import format_kpis, format_observation
from .simulation import repair_state_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m traci_layer", description="LuST Luxembourg TraCI observation layer")
    p.add_argument("--cfg", type=Path, default=DEFAULT_SUMOCFG, help="SUMO .sumocfg (default: LuST dua.actuated)")
    p.add_argument("--scenario", default="S0", help="Scenario label (S0..S4)")
    p.add_argument("--duration", type=float, default=300, help="Observation duration in seconds")
    p.add_argument("--interval", type=float, default=60, help="Seconds between two observations")
    p.add_argument("--start-at", type=float, default=None,
                   help="Fast-forward (no collection) to this simulation time first, e.g. 25200 = 07:00")
    p.add_argument("--load-state", type=Path, default=None, help="Start from a saved SUMO state")
    p.add_argument("--save-state", type=Path, default=None, help="Save the state when observation starts")
    p.add_argument("--gui", action="store_true", help="Use sumo-gui")
    p.add_argument("--libsumo", action="store_true", help="Use libsumo (faster, no GUI)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--lane-scope", default="tls", choices=["tls", "all", "none"])
    p.add_argument("--no-edges", action="store_true", help="Skip edge collection (faster)")
    p.add_argument("--details", action="store_true", help="Export per-vehicle/edge/lane/TLS tables")
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR, help="Export folder")
    p.add_argument("--no-export", action="store_true")
    p.add_argument("--emergency-from", default=None, help="Edge where an emergency vehicle starts")
    p.add_argument("--emergency-to", default=None, help="Destination edge of the emergency vehicle")
    p.add_argument("--emergency-at", type=float, default=None, help="Departure time (default: now)")
    p.add_argument("--emergency-type", default="emergency_bluelight", choices=["emergency_bluelight", "emergency_plain"])
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    run_name = f"{args.scenario}_{time.strftime('%Y%m%d_%H%M%S')}"
    sumo_cfg = SumoConfig(
        sumocfg=args.cfg, gui=args.gui, use_libsumo=args.libsumo, load_state=args.load_state, seed=args.seed,
        output_dir=None if args.no_export else args.out / run_name / "sumo_outputs",
        additional_files=[EMERGENCY_VTYPES_FILE] if EMERGENCY_VTYPES_FILE.exists() else [],
    )
    col_cfg = CollectorConfig(snapshot_interval=args.interval, collect_edges=not args.no_edges,
                              lane_scope=None if args.lane_scope == "none" else args.lane_scope,
                              include_details=args.details)
    t0 = time.perf_counter()
    with SumoConnection(sumo_cfg) as api:
        if args.start_at is not None and api.simulation.getTime() < args.start_at:
            print(f"Fast-forward to {clock(args.start_at)} (no collection)...", flush=True)
            api.simulationStep(args.start_at)
        if args.save_state:
            args.save_state.parent.mkdir(parents=True, exist_ok=True)
            api.simulation.saveState(str(args.save_state))
            repair_state_file(args.save_state)
            print(f"State saved: {args.save_state}")
        if args.emergency_from and args.emergency_to:
            spec = EmergencyVehicleSpec("emergency_1", args.emergency_from, args.emergency_to,
                                        depart=args.emergency_at if args.emergency_at is not None else "now",
                                        type_id=args.emergency_type)
            edges = spawn_emergency_vehicle(api, spec)
            print(f"Emergency vehicle {spec.vehicle_id} scheduled: {len(edges)} edges, depart {spec.depart}")

        print("Initialising collector (subscriptions)...", flush=True)
        collector = TrafficDataCollector(api, col_cfg, sumocfg=args.cfg, scenario=args.scenario, run_id=run_name)
        exporter = None if args.no_export else RunExporter(args.out, run_name)
        for obs in collector.run(duration=args.duration, observe_every=args.interval):
            print(format_observation(obs), flush=True)
            if exporter:
                exporter.write_observation(obs)
        kpis = collector.kpis()
        print(format_kpis(kpis))
        if exporter:
            files = exporter.finalize(collector)
            print(f"Exported to {exporter.dir}:")
            for name, path in files.items():
                print(f"  - {name}: {path.name}")
    print(f"Wall-clock time: {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
