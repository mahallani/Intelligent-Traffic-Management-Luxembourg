"""Evaluate the detection agent on SIMULATED incidents (ground truth known): a lane is almost blocked
(speed limit 0.05 m/s) from 07:20 to 07:40. Runs fixed-time control (S0), per scale and seed:
one run without incident (false alerts) and one run per incident lane.

    python scripts/simulation/evaluate_detection.py --scale 1 --seeds 1 2 3

Outputs: sumo/lust_4_intersections/output/experiments_v1/detection/<run>/ and a summary CSV
detection_summary_x<scale>.csv (rows appended per run, existing runs skipped)."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.orchestrator import Incident, run_episode  # noqa: E402

DET = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "detection"
LANES = ["-31070#4_1", "--31070#8_1"]       # busiest approaches (to -29958 and -28692)
START, END = 26400.0, 27600.0
COLS = ["run", "scale", "seed", "incident_lane", "detected", "detection_delay_s", "detecting_rule",
        "false_alerts", "false_alerts_per_hour", "alerts_total", "data_origin"]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    a = p.parse_args(argv)
    summary = DET / f"detection_summary_x{a.scale:g}.csv"
    for seed in a.seeds:
        for lane in [None] + LANES:
            name = f"S0_x{a.scale:g}_seed{seed}_" + ("no_incident" if lane is None else "blocked_" + lane.replace("#", "_"))
            out = DET / name
            if (out / "kpis.json").exists():
                print("skip", name); continue
            inc = Incident(lane, START, END) if lane else None
            k = run_episode("S0_fixed_time", a.scale, seed, out, incident=inc)
            with open(out / "alerts.csv", encoding="utf-8") as fh:
                alerts = list(csv.DictReader(fh, delimiter=";"))
            edge = lane.rsplit("_", 1)[0] if lane else None
            true = [x for x in alerts if edge and x["lane"].rsplit("_", 1)[0] == edge and START <= float(x["raised_s"]) <= END + 60]
            false = [x for x in alerts if x not in true]
            row = {"run": name, "scale": a.scale, "seed": seed, "incident_lane": lane or "", "detected": bool(true) if lane else "",
                   "detection_delay_s": (float(true[0]["raised_s"]) - START) if true else "",
                   "detecting_rule": true[0]["rule"] if true else "", "false_alerts": len(false),
                   "false_alerts_per_hour": round(len(false) / ((k["end"] - k["begin"] - k["warmup_s"]) / 3600), 2),
                   "alerts_total": len(alerts), "data_origin": DATA_ORIGIN}
            new = not summary.exists()
            summary.parent.mkdir(parents=True, exist_ok=True)
            with open(summary, "a", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=COLS, delimiter=";")
                if new:
                    w.writeheader()
                w.writerow(row)
            print(json.dumps(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
