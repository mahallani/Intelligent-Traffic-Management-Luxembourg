"""Compare REAL PCH counts (2025, Tue-Thu mean, 07:00-08:00, both directions = DIRECTION 3, all vehicles U)
with SIMULATED LuST flows on the matched LuST edges (vehicles entering the edge 07:00-08:00, both directions),
then test ONE global demand factor with a hold-out split (fit on half of the posts, evaluate on the other half).

Indicator common to both sides: vehicles per hour on a road section (count). Nothing else is compared.
Edge matching = nearest LuST edge (and its reverse) within 60 m of the PCH coordinates (pch_posts_v1.csv),
road name of the LuST edge given for manual checking. The Kirchberg 4-signal zone contains NO PCH post:
this comparison concerns the LuST network around it and is NOT a calibration of the Kirchberg scenario.

Inputs : data/processed/tasks/task_C_real_pch_potential_demand_profiles_v1.csv (real),
         sumo/lust_4_intersections/build_cache/vehroutes_0700_0830.xml.gz (simulated LuST run, 07:00-08:30)
         LuSTScenario/scenario/lust.net.xml (edge names)
Outputs: data/reports/pch_vs_lust_0700_0800_<tag>.csv and .json  (never overwritten)
Usage  : python scripts/data_pipeline/compare_pch_lust_v1.py --tag v1
"""
import argparse
import collections
import csv
import gzip
import json
import math
import statistics as st
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, REPORTS, ROOT, now_utc, safe_path  # noqa: E402

PROFILES = DATA / "processed/tasks/task_C_real_pch_potential_demand_profiles_v1.csv"
VEHROUTES = ROOT / "sumo/lust_4_intersections/build_cache/vehroutes_0700_0830.xml.gz"
NET = ROOT / "LuSTScenario/scenario/lust.net.xml"


def geh(m, c):
    return math.sqrt(2 * (m - c) ** 2 / (m + c)) if m + c > 0 else 0.0


def sim_counts(t0=25200.0, t1=28800.0):
    cnt = collections.Counter()
    with gzip.open(VEHROUTES) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "vehicle":
                continue
            r = el.find("route")
            if r is None and el.find("routeDistribution") is not None:
                r = el.find("routeDistribution").findall("route")[-1]
            if r is not None and r.get("exitTimes"):
                edges = r.get("edges").split()
                ex = [float(x) for x in r.get("exitTimes").split()]
                for e, t in zip(edges, [float(el.get("depart"))] + ex[:-1]):
                    if t0 <= t < t1:
                        cnt[e] += 1
            el.clear()
    return cnt


def edge_names(wanted):
    names = {}
    for _, el in ET.iterparse(str(NET), events=("end",)):
        if el.tag == "edge" and el.get("id") in wanted:
            names[el.get("id")] = el.get("name") or ""
        if el.tag in ("edge", "lane", "connection", "junction", "tlLogic"):
            el.clear()
    return names


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1")
    a = p.parse_args(argv)
    out_csv = safe_path(REPORTS / f"pch_vs_lust_0700_0800_{a.tag}.csv")
    out_json = safe_path(REPORTS / f"pch_vs_lust_0700_0800_{a.tag}.json")
    cnt = sim_counts()
    rows = []
    with open(PROFILES, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            if r["hour_start_local"] != "7" or r["DIRECTION"] != "3" or not r["lust_edge_candidates_unverified"]:
                continue
            cands = [x.split("@") for x in r["lust_edge_candidates_unverified"].split("|")]
            base = cands[0][0].lstrip("-")
            pair = sorted({e for e, _ in cands if e.lstrip("-") == base})
            rows.append({"POSTE_ID": r["POSTE_ID"], "LOCALITE": r["LOCALITE"], "ROUTE": r["ROUTE"],
                         "pch_count_veh_h_real": float(r["mean_count_tue_thu"]), "pch_days": int(r["n_days"]),
                         "lust_edges": "|".join(pair), "match_distance_m": cands[0][1].rstrip("m"),
                         "lust_count_veh_h_simulated": sum(cnt.get(e, 0) for e in pair)})
    names = edge_names({e for r in rows for e in r["lust_edges"].split("|")})
    for r in rows:
        r["lust_edge_names"] = "|".join(sorted({names.get(e, "") for e in r["lust_edges"].split("|")}))
    rows.sort(key=lambda r: int(r["POSTE_ID"]))
    fit = [r for i, r in enumerate(rows) if i % 2 == 0]       # deterministic split by POSTE_ID order
    test = [r for i, r in enumerate(rows) if i % 2 == 1]
    k = st.median(r["pch_count_veh_h_real"] / r["lust_count_veh_h_simulated"] for r in fit if r["lust_count_veh_h_simulated"] > 0)

    def errors(rs, factor):
        g = [geh(factor * r["lust_count_veh_h_simulated"], r["pch_count_veh_h_real"]) for r in rs]
        ape = [abs(factor * r["lust_count_veh_h_simulated"] - r["pch_count_veh_h_real"]) / r["pch_count_veh_h_real"] for r in rs]
        return {"n_posts": len(rs), "mean_GEH": round(st.mean(g), 2), "share_GEH_lt_5": round(sum(x < 5 for x in g) / len(g), 2),
                "MAPE_pct": round(100 * st.mean(ape), 1)}
    for r in rows:
        r["split"] = "fit" if r in fit else "test"
        r["ratio_real_over_sim"] = round(r["pch_count_veh_h_real"] / r["lust_count_veh_h_simulated"], 3) if r["lust_count_veh_h_simulated"] else ""
        r["GEH_before"] = round(geh(r["lust_count_veh_h_simulated"], r["pch_count_veh_h_real"]), 2)
        r["GEH_after_global_factor"] = round(geh(k * r["lust_count_veh_h_simulated"], r["pch_count_veh_h_real"]), 2)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    rep = {"generated_utc": now_utc(), "indicator": "vehicles/hour, both directions, 07:00-08:00",
           "real": "PCH 2025, Tue-Thu mean, DIRECTION 3, VEHICULE U", "simulated": "LuST (~2015) run 07:00-08:30, entries per edge",
           "matched_posts": len(rows), "global_factor_fitted_on_fit_half": round(k, 3),
           "before": {"fit": errors(fit, 1.0), "test": errors(test, 1.0)},
           "after_global_factor": {"fit": errors(fit, k), "test": errors(test, k)},
           "interpretation_rule": "GEH < 5 is the usual acceptance threshold for hourly link counts",
           "limits": ["edge matching by distance only (road names listed for manual check)",
                      "2025 counts vs ~2015 LuST demand", "no PCH post inside the Kirchberg 4-signal zone",
                      "a single global factor cannot fix local mismatches; not applied to the scenario automatically"]}
    out_json.write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k2: rep[k2] for k2 in ("matched_posts", "global_factor_fitted_on_fit_half", "before", "after_global_factor")}, indent=1))
    for r in rows:
        print(r["POSTE_ID"], r["LOCALITE"], r["ROUTE"], r["lust_edge_names"], r["pch_count_veh_h_real"], r["lust_count_veh_h_simulated"], r["GEH_before"], r["split"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
