"""Scenario B detail (SIMULATED, 2026-10-22): what happens at Carrefour 4 (-29958) while lane -31070#4_1 is blocked
(07:20-07:40), compared with the same seed without the incident. Reads only the demo_scenarios_v1/B run outputs.

- forecasts for Carrefour 4 whose TARGET time is inside the incident window: MAE of the model vs persistence;
- S3 phase changes at Carrefour 4 in the window, by phase and by source (agent / safety max-green);
  phase 4 (GGGGrrrr) is the one that serves -31070#4_0/_1, i.e. the blocked approach (from the net file);
- alerts by rule and lane.

    python scripts/simulation/analyze_demo_incident_v1.py --tag a
Writes demo_scenarios_v1/incident_tls4_analysis_<tag>.csv and .md (never overwritten).
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sumo" / "lust_4_intersections" / "output" / "demo_scenarios_v1"
TLS, T0, T1, PHASE_BLOCKED = "-29958", 26400.0, 27600.0, "4"


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="a")
    tag = ap.parse_args().tag
    md, cs = OUT / f"incident_tls4_analysis_{tag}.md", OUT / f"incident_tls4_analysis_{tag}.csv"
    for f in (md, cs):
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    rows = []
    for s in ("S0_fixed_time", "S3_rl_qlearning"):
        for seed in (61, 62, 63):
            for v in ("no_incident", "incident"):
                d = OUT / "B" / f"{s}_x5_seed{seed}_{v}"
                r = {"run": d.name, "strategy": s, "seed": seed, "incident": v == "incident"}
                for h in (5, 10, 15):
                    p = [x for x in rd(d / "predictions.csv") if x["tls"] == TLS and int(x["horizon_min"]) == h
                         and T0 <= float(x["target_s"]) < T1]
                    r[f"n_{h}"] = len(p)
                    r[f"mae_model_{h}"] = round(sum(abs(float(x["error"])) for x in p) / len(p), 2) if p else None
                    r[f"mae_persistence_{h}"] = round(sum(abs(float(x["error_persistence"])) for x in p) / len(p), 2) if p else None
                    r[f"mean_observed_{h}"] = round(sum(float(x["observed"]) for x in p) / len(p), 2) if p else None
                dec = [x for x in rd(d / "decisions.csv") if x["tls"] == TLS and T0 <= float(x["time_s"]) < T1]
                c = collections.Counter((x["from_phase"], x["reason"]) for x in dec)
                r["phase4_ended_by_agent"] = c[(PHASE_BLOCKED, "agent_decision")]
                r["phase4_ended_by_max_green"] = c[(PHASE_BLOCKED, "max_green")]
                r["all_phase_changes"] = len(dec)
                r["max_green_all_phases"] = sum(v for (ph, why), v in c.items() if why == "max_green")
                al = [a for a in rd(d / "alerts.csv") if float(a["raised_s"]) >= 25500]
                r["alerts"] = json.dumps(dict(collections.Counter(f"{a['rule']}@{a['lane']}" for a in al)), ensure_ascii=False)
                r["data_origin"] = "SIMULATED_sumo_lust_kirchberg_4tls"
                rows.append(r)
    with open(cs, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    L = [f"# Scénario B – détail au Carrefour 4 ({tag}) – SIMULÉ", "",
         "Fenêtre : 07:20-07:40 (cible des prévisions dans la fenêtre). Phase 4 = vert de l'approche bloquée (-31070#4).", "",
         "| Run | MAE modèle +5 / +10 / +15 | MAE persistance +5 / +10 / +15 | Arrêtés observés (moy., +5) | Phase 4 terminée par l'agent | Phase 4 terminée par le vert max | Alertes |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        ph4 = (r["phase4_ended_by_agent"], r["phase4_ended_by_max_green"]) if r["strategy"].startswith("S3") else ("–", "–")
        L.append(f"| {r['run']} | {r['mae_model_5']} / {r['mae_model_10']} / {r['mae_model_15']} | "
                 f"{r['mae_persistence_5']} / {r['mae_persistence_10']} / {r['mae_persistence_15']} | {r['mean_observed_5']} | "
                 f"{ph4[0]} | {ph4[1]} | {r['alerts']} |")
    L += ["", "Source : predictions.csv, decisions.csv, alerts.csv des runs demo_scenarios_v1/B."]
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
