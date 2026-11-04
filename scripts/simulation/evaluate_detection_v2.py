"""Detection evaluation v2 on SIMULATED incidents (ground truth known): precision, recall, F1, false alerts/h,
for two variants of the detection agent (same simulations, same incidents):
  rules : v1 rules (congestion = >= 8 halted for >= 60 s; stalled = a vehicle stopped >= 150 s)
  gated : same, but the congestion rule fires only when the signal's halted vehicles exceed the cascade
          forecast made 5 min earlier by >= 5 vehicles (unexpected congestion). Thresholds fixed a priori.
  discharge : "blocked lane" rule (>= 20 s of green in 90 s, >= 3 halted at each sample, no vehicle through
          the stop line) instead of the congestion rule, plus the stalled rule. Thresholds fixed a priori.
Incident = lane speed limit 0.05 m/s from 07:20 to 07:40 on one of 2 busy approaches; control = S0.

    python scripts/simulation/evaluate_detection_v2.py --variant rules --scales 1 3 5 --seeds 1 2 3
    python scripts/simulation/evaluate_detection_v2.py --variant gated --scales 1 3 5 --seeds 1 2 3
    python scripts/simulation/evaluate_detection_v2.py --summarize

Definitions (per run, alerts raised after the 300-s warm-up):
  true alert  = alert on the incident edge raised between incident start and end + 60 s;  false alert = any other
  recall = incidents with >= 1 true alert / incidents;  precision = true alerts / all alerts
  F1 = 2PR/(P+R);  false alerts per hour = false alerts / (runs x 0.917 h)"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.orchestrator import Incident, run_episode  # noqa: E402

DET = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "detection_v2"
LANES = ["-31070#4_1", "--31070#8_1"]
START, END = 26400.0, 27600.0
HOURS = (28800 - 25200 - 300) / 3600


def run(variant, scales, seeds, folder=None):
    for scale in scales:
        for seed in seeds:
            for lane in [None] + LANES:
                name = f"x{scale:g}_seed{seed}_" + ("no_incident" if lane is None else "blocked_" + lane.replace("#", "_"))
                out = DET / (folder or variant) / name
                if (out / "kpis.json").exists():
                    continue
                inc = Incident(lane, START, END) if lane else None
                run_episode("S0_fixed_time", scale, seed, out, incident=inc, detection_mode=variant)
                print("done", variant, name, flush=True)


def summarize(tag):
    rows, summary = [], []
    for vdir in sorted(p for p in DET.iterdir() if p.is_dir()):
        for rdir in sorted(vdir.iterdir()):
            if "INCOMPLETE" in rdir.name or not (rdir / "kpis.json").exists():
                continue
            k = json.loads((rdir / "kpis.json").read_text())
            with open(rdir / "alerts.csv", encoding="utf-8") as fh:
                alerts = [x for x in csv.DictReader(fh, delimiter=";") if float(x["raised_s"]) >= 25200 + 300]
            lane = (k.get("incident") or {}).get("lane")
            edge = lane.rsplit("_", 1)[0] if lane else None
            true = [x for x in alerts if edge and x["lane"].rsplit("_", 1)[0] == edge and START <= float(x["raised_s"]) <= END + 60]
            rows.append({"variant": vdir.name, "run": rdir.name, "scale": k["scale"], "seed": k["seed"], "incident_lane": lane or "",
                         "true_alerts": len(true), "false_alerts": len(alerts) - len(true),
                         "detected": (bool(true) if lane else ""),
                         "delay_s": (min(float(x["raised_s"]) for x in true) - START) if true else "",
                         "suppressed_by_forecast": k["detection"].get("suppressed_by_forecast", 0), "data_origin": DATA_ORIGIN})
    for v in sorted({r["variant"] for r in rows}):
        for sc in sorted({r["scale"] for r in rows}) + ["all"]:
            rs = [r for r in rows if r["variant"] == v and (sc == "all" or r["scale"] == sc)]
            inc = [r for r in rs if r["incident_lane"]]
            ta, fa = sum(r["true_alerts"] for r in rs), sum(r["false_alerts"] for r in rs)
            rec = sum(r["detected"] is True for r in inc) / len(inc) if inc else None
            prec = ta / (ta + fa) if ta + fa else None
            f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
            delays = [r["delay_s"] for r in inc if r["delay_s"] != ""]
            summary.append({"variant": v, "scale": sc, "runs": len(rs), "incidents": len(inc),
                            "recall": None if rec is None else round(rec, 3), "precision": None if prec is None else round(prec, 3),
                            "F1": round(f1, 3), "false_alerts_per_hour": round(fa / (len(rs) * HOURS), 2),
                            "mean_delay_s": round(sum(delays) / len(delays)) if delays else None, "data_origin": DATA_ORIGIN})
    for name, data in ((f"detection_v2_runs_{tag}.csv", rows), (f"detection_v2_summary_{tag}.csv", summary)):
        f = DET / name
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]), delimiter=";")
            w.writeheader()
            w.writerows(data)
    for s in summary:
        print(s)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=["rules", "gated", "discharge"])
    p.add_argument("--scales", type=float, nargs="+", default=[1, 3, 5])
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--summarize", action="store_true")
    p.add_argument("--tag", default="v1")
    p.add_argument("--folder", default=None, help="results sub-folder (default = variant), e.g. discharge_confirm_seeds11_12")
    a = p.parse_args(argv)
    if a.variant:
        run(a.variant, a.scales, a.seeds, a.folder)
    if a.summarize:
        summarize(a.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
