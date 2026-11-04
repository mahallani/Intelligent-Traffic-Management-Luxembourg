"""Non-regression check of the ambulance tracking (2026-10-22). SIMULATED.

Re-runs reference configurations into a NEW folder (never overwrites) and compares them with the reference outputs:
KPIs (every numeric field except wall-clock time), safety, emergency result and priority actions, and the
'ambulance' line of tripinfo.xml. Prints the tracker events of each ambulance run.

    python scripts/simulation/check_ambulance_tracking_v1.py --outdir demo_scenarios_v1_check_ambulance
Exit code 1 if anything differs.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.orchestrator import Incident, make_controller, run_episode  # noqa: E402

OUTPUT = ROOT / "sumo" / "lust_4_intersections" / "output"
QTABLE = OUTPUT / "experiments_v1" / "rl" / "qtable_v4_FROZEN_ep26_eval.json"
INC = ("-31070#4_1", 26400.0, 27600.0)
REF = OUTPUT / "demo_scenarios_v1"
# name -> (strategy, seed, incident, emergency_at, priority, reference run dir or None, expected values or None)
CASES = {
    "S3_x5_seed61_incident_ambulance_prio": ("S3_rl_qlearning", 61, True, 26400.0, True,
                                             REF / "B" / "S3_rl_qlearning_x5_seed61_incident_ambulance_prio", None),
    "S3_x5_seed61_incident_ambulance": ("S3_rl_qlearning", 61, True, 26400.0, False,
                                        REF / "B" / "S3_rl_qlearning_x5_seed61_incident_ambulance", None),
    "S0_x5_seed61_no_ambulance": ("S0_fixed_time", 61, False, None, False, REF / "A" / "S0_fixed_time_x5_seed61", None),
    # same settings as the Windows app run 20261022_110813 (sumo-gui, TraCI): values copied from its kpis.json/tripinfo
    "S0_x5_seed1_ambulance_prio": ("S0_fixed_time", 1, False, 26400.0, True, None,
                                   {"avg_travel_time_s": 132.07, "emergency.travel_time_s": 189.0,
                                    "emergency.waiting_time_s": 30.0, "ambulance.depart": "26417.00",
                                    "ambulance.arrival": "26606.00", "safety": 0,
                                    "requests": [26431.0, 26481.0, 26506.0, 26552.0]}),
}
SKIP = {"wall_clock_s", "backend", "data_origin", "programs_at_start"}


def amb_trip(run):
    e = next((e for e in ET.parse(run / "tripinfo.xml").getroot().iter("tripinfo") if e.get("id") == "ambulance"), None)
    return dict(e.attrib) if e is not None else None


def compare(new, ref):
    kn, kr = json.loads((new / "kpis.json").read_text(encoding="utf-8")), json.loads((ref / "kpis.json").read_text(encoding="utf-8"))
    diffs = [f"{k}: {kr[k]} -> {kn.get(k)}" for k in kr if k not in SKIP and not isinstance(kr[k], dict) and kn.get(k) != kr[k]]
    for k in ("safety", "actuator", "controller", "incident"):
        if kr.get(k) != kn.get(k):
            diffs.append(f"{k} differs")
    if kr.get("emergency") or kn.get("emergency"):
        a, b = dict(kr.get("emergency") or {}), dict(kn.get("emergency") or {})
        if a != b:
            diffs.append(f"emergency: {a} -> {b}")
        ta, tb = amb_trip(ref), amb_trip(new)
        if ta != tb:
            diffs.append(f"tripinfo ambulance: {ta} -> {tb}")
    return diffs


def check_expected(new, exp):
    k = json.loads((new / "kpis.json").read_text(encoding="utf-8"))
    tr = amb_trip(new) or {}
    got = {"avg_travel_time_s": k["avg_travel_time_s"], "emergency.travel_time_s": k["emergency"]["travel_time_s"],
           "emergency.waiting_time_s": k["emergency"]["waiting_time_s"], "ambulance.depart": tr.get("depart"),
           "ambulance.arrival": tr.get("arrival"), "safety": k["safety"]["total_violations"],
           "requests": [a["time"] for a in k["emergency"]["actions"] if a["action"] == "request"]}
    return [f"{x}: expected {exp[x]} got {got[x]}" for x in exp if got[x] != exp[x]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="demo_scenarios_v1_check_ambulance")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    out_root = OUTPUT / a.outdir
    bad = 0
    for name, (strat, seed, inc, ev, prio, ref, exp) in CASES.items():
        if a.only and name not in a.only:
            continue
        out = out_root / name
        if not (out / "kpis.json").exists():
            ctrl = make_controller(strat, qtable=QTABLE) if strat.startswith("S3") else make_controller(strat)
            run_episode(strat, 5.0, seed, out, controller=ctrl, detection_mode="discharge",
                        incident=Incident(*INC) if inc else None, emergency_at=ev, emergency_priority=prio)
        diffs = compare(out, ref) if ref else check_expected(out, exp)
        bad += bool(diffs)
        print(f"{'IDENTIQUE' if not diffs else 'DIFFÉRENT'} {name} (référence: {ref.relative_to(OUTPUT) if ref else 'run Windows 20261022_110813'})")
        for d in diffs:
            print("   ", d)
        ev_file = out / "ambulance_events.csv"
        if ev_file.exists():
            print("   événements:", ev_file.read_text(encoding="utf-8").count("\n") - 1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
