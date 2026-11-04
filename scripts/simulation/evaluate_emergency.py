"""Emergency-vehicle priority evaluated ON ITS OWN (separate from the RL agent and the controllers).

An ambulance (vClass emergency) enters the avenue at 07:20 and crosses the 4 signals. For each control
strategy and seed: run without priority, then with the EmergencyPriorityAgent. Measured: ambulance travel
and waiting time, effect on all other vehicles, safety violations (SafetyMonitor). SIMULATED.

    python scripts/simulation/evaluate_emergency.py --strategies S0_fixed_time S2_demand_gap --scale 5 --seeds 1 2 3
    python scripts/simulation/evaluate_emergency.py --summarize --tag v1"""
import argparse
import csv
import json
import statistics as stt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.orchestrator import make_controller, run_episode  # noqa: E402

OUT = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "emergency"
EV_AT = 26400.0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--strategies", nargs="+", default=["S0_fixed_time", "S2_demand_gap"])
    p.add_argument("--scale", type=float, default=5.0)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--summarize", action="store_true")
    p.add_argument("--tag", default="v1")
    p.add_argument("--folder", default="emergency", help="results sub-folder of experiments_v1 (emergency_v2 = after the 2026-10-12 fix)")
    a = p.parse_args(argv)
    global OUT
    OUT = OUT.parent / a.folder
    if not a.summarize:
        for strat in a.strategies:
            for seed in a.seeds:
                for prio in (False, True):
                    out = OUT / f"{strat}_x{a.scale:g}_seed{seed}_{'priority' if prio else 'no_priority'}"
                    if (out / "kpis.json").exists():
                        continue
                    run_episode(strat, a.scale, seed, out, controller=make_controller(strat), emergency_at=EV_AT, emergency_priority=prio)
                    print("done", out.name, flush=True)
        return 0
    rows = []
    for d in sorted(OUT.iterdir()):
        if not (d / "kpis.json").exists():
            continue
        k = json.loads((d / "kpis.json").read_text())
        e = k["emergency"]
        rows.append({"run": d.name, "strategy": k["strategy"], "scale": k["scale"], "seed": k["seed"], "priority": e["priority"],
                     "ambulance_travel_s": e["travel_time_s"], "ambulance_waiting_s": e["waiting_time_s"],
                     "priority_actions": len(e["actions"]), "all_vehicles_avg_travel_s": k["avg_travel_time_s"],
                     "all_vehicles_avg_waiting_s": k["avg_waiting_time_s"], "safety_violations": k["safety"]["total_violations"],
                     "data_origin": DATA_ORIGIN})
    out = OUT / f"emergency_summary_{a.tag}.csv"
    if out.exists():
        sys.exit(f"{out} exists")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    for strat in sorted({r["strategy"] for r in rows}):
        for prio in (False, True):
            rs = [r for r in rows if r["strategy"] == strat and r["priority"] == prio and r["ambulance_travel_s"] is not None]
            if rs:
                print(strat, "priority" if prio else "no priority", "ambulance travel", round(stt.mean(r["ambulance_travel_s"] for r in rs), 1),
                      "waiting", round(stt.mean(r["ambulance_waiting_s"] for r in rs), 1), "all-veh travel",
                      round(stt.mean(r["all_vehicles_avg_travel_s"] for r in rs), 2), "violations", sum(r["safety_violations"] for r in rs), "n", len(rs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
