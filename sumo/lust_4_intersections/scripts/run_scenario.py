"""
Run the Kirchberg 4-signal scenario with TraCI and print the observation reports of the
project's TraCI layer (traci_layer).

Usage (PowerShell, project root):
    python sumo\\lust_4_intersections\\scripts\\run_scenario.py                       # 07:00-08:00, real LuST demand
    python sumo\\lust_4_intersections\\scripts\\run_scenario.py --gui                 # same in sumo-gui
    python sumo\\lust_4_intersections\\scripts\\run_scenario.py --scale 5 --interval 600
    python sumo\\lust_4_intersections\\scripts\\run_scenario.py --ambulance-at 26400  # add an emergency vehicle at 07:20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from traci_layer import (CollectorConfig, RunExporter, SumoConfig, SumoConnection, TrafficDataCollector,  # noqa: E402
                         format_kpis, format_observation)

CFG = HERE / "kirchberg_4tls.sumocfg"
ROUTES = HERE / "routes" / "kirchberg_0700_0800.rou.xml"
AVENUE_EAST = ["--31070#8", "--31070#7", "--31070#6", "--31070#5", "--31070#4"]


def main() -> int:
    p = argparse.ArgumentParser(description="Kirchberg 4-signal scenario (LuST) with TraCI")
    p.add_argument("--gui", action="store_true")
    p.add_argument("--scale", type=float, default=1.0, help="demand factor (1 = real LuST, 5-6 = congested)")
    p.add_argument("--until", type=float, default=28800, help="end time in s (28800 = 08:00)")
    p.add_argument("--interval", type=float, default=900, help="seconds between reports")
    p.add_argument("--ambulance-at", type=float, default=None, help="insert an emergency vehicle at this time")
    p.add_argument("--ambulance-type", default="emergency_plain", choices=["emergency_plain", "emergency_bluelight"])
    p.add_argument("--export", action="store_true", help="write JSONL/CSV/KPIs to output/")
    args = p.parse_args()

    cfg = SumoConfig(sumocfg=CFG, gui=args.gui, label="kirchberg", output_dir=HERE / "output" / "sumo",
                     extra_args=["--scale", str(args.scale)])
    with SumoConnection(cfg) as api:
        if args.ambulance_at is not None:
            api.route.add("ev_route", AVENUE_EAST)
            api.vehicle.add("ambulance", "ev_route", typeID=args.ambulance_type, depart=str(args.ambulance_at),
                            departLane="best", departSpeed="max")
        col = TrafficDataCollector(api, CollectorConfig(snapshot_interval=args.interval, lane_scope="tls",
                                                        bus_route_files=[ROUTES], include_details=args.export),
                                   sumocfg=CFG, scenario=f"kirchberg_x{args.scale:g}")
        exporter = RunExporter(HERE / "output", col.run_id) if args.export else None
        for obs in col.run(until=args.until, observe_every=args.interval, stop_when_empty=False):
            print(format_observation(obs), flush=True)
            if exporter:
                exporter.write_observation(obs)
        print(format_kpis(col.kpis()))
        if exporter:
            exporter.finalize(col)
            print(f"Exported to {exporter.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
