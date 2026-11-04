"""Aggregate the evaluation runs (seeds 1-3, no incident) and compare each strategy with the
fixed-time reference S0. All numbers are SIMULATED (SUMO, LuST demand, Kirchberg 4 signals).

    python scripts/simulation/compare_strategies.py --tag v1

Writes (refuses to overwrite) in sumo/lust_4_intersections/output/experiments_v1/results/:
  kpi_runs_<tag>.csv, kpi_summary_<tag>.csv, kpi_vs_baseline_<tag>.csv, RESULTS_<tag>.md"""
import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sumo" / "lust_4_intersections" / "output"
KPIS = [("avg_travel_time_s", "Temps de trajet moyen (s)", -1), ("avg_waiting_time_s", "Attente moyenne (s)", -1),
        ("avg_time_loss_s", "Temps perdu moyen (s)", -1), ("p95_travel_time_s", "Temps de trajet P95 (s)", -1),
        ("avg_queue_veh", "File moyenne (véh. arrêtés)", -1), ("max_queue_veh", "File max (véh.)", -1),
        ("avg_queue_m", "File moyenne (m)", -1), ("arrived", "Véhicules arrivés", 1),
        ("avg_depart_delay_s", "Retard d'insertion moyen (s)", -1), ("waiting_insertion_at_end", "Véh. bloqués à l'entrée (fin)", -1),
        ("co2_kg", "CO2 (kg)", -1), ("nox_g", "NOx (g)", -1), ("fuel_kg", "Carburant (kg)", -1),
        ("teleports", "Téléportations", -1)]
ORDER = ["S0_fixed_time", "S1_actuated", "S2_demand_gap", "S2b_max_pressure", "S3_rl_qlearning"]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v1", help="tag of the result files")
    p.add_argument("--experiments", default="v1", help="read runs from output/experiments_<this>/runs")
    a = p.parse_args(argv)
    EXP = OUT / f"experiments_{a.experiments}"
    res = EXP / "results"
    outs = {k: res / f"{k}_{a.tag}.{'md' if k == 'RESULTS' else 'csv'}" for k in ("kpi_runs", "kpi_summary", "kpi_vs_baseline", "RESULTS")}
    for f in outs.values():
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    res.mkdir(parents=True, exist_ok=True)
    runs = []
    for f in sorted((EXP / "runs").glob("*/kpis.json")):
        k = json.loads(f.read_text(encoding="utf-8"))
        if "incident" in f.parent.name or "INCOMPLETE" in f.parent.name or k["seed"] not in (1, 2, 3):
            continue
        k["run"] = f.parent.name
        runs.append(k)
    cols = ["run", "strategy", "scale", "seed", "backend"] + [c for c, _, _ in KPIS] + \
           ["completed_trips", "unfinished_trips_at_end", "total_waiting_time_all_h", "total_time_loss_all_h", "pmx_g",
            "discarded_not_inserted", "collisions", "data_origin"]
    with open(outs["kpi_runs"], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(runs)
    groups = {}
    for r in runs:
        groups.setdefault((r["scale"], r["strategy"]), []).append(r)
    summary = []
    for (scale, strat), rs in sorted(groups.items(), key=lambda x: (x[0][0], ORDER.index(x[0][1]))):
        row = {"scale": scale, "strategy": strat, "n_seeds": len(rs), "seeds": " ".join(str(r["seed"]) for r in rs)}
        for c, _, _ in KPIS:
            v = [r[c] for r in rs if r.get(c) is not None]
            row[f"{c}_mean"] = round(st.mean(v), 2) if v else None
            row[f"{c}_std"] = round(st.stdev(v), 2) if len(v) > 1 else 0.0
        summary.append(row)
    with open(outs["kpi_summary"], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]), delimiter=";")
        w.writeheader()
        w.writerows(summary)
    base = {r["scale"]: r for r in summary if r["strategy"] == "S0_fixed_time"}
    comp = []
    for r in summary:
        b = base.get(r["scale"])
        row = {"scale": r["scale"], "strategy": r["strategy"]}
        for c, _, _ in KPIS:
            bv, v = b.get(f"{c}_mean"), r.get(f"{c}_mean")
            row[f"{c}_pct_vs_S0"] = round(100 * (v - bv) / bv, 1) if bv not in (None, 0) and v is not None else None
        comp.append(row)
    with open(outs["kpi_vs_baseline"], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(comp[0]), delimiter=";")
        w.writeheader()
        w.writerows(comp)
    # ---------- markdown report
    md = [f"# Résultats de simulation – Kirchberg, 4 feux ({a.tag})", "",
          "**Toutes les valeurs sont SIMULÉES** (SUMO 1.27.1, demande LuST 07:00–08:00 ~2015, réseau LuST). "
          "Ce ne sont pas des mesures réelles et le modèle n'est pas calibré sur des données réelles.", "",
          "Méthode : 3 graines SUMO (1, 2, 3) par stratégie ; files mesurées toutes les 5 s après 300 s de mise en route ; "
          "temps de trajet / attente / émissions depuis `tripinfo` (modèle d'émission HBEFA de SUMO). "
          "Graines de réglage (50), de validation RL (60, 61) et d'entraînement RL (101+) distinctes des graines d'évaluation.", ""]
    for scale in sorted(base):
        md += [f"## Demande ×{scale:g}" + (" (trafic LuST réel)" if scale == 1 else " (congestion)"), "",
               "| Indicateur | " + " | ".join(s for s in ORDER if (scale, s) in groups) + " |",
               "|---|" + "---|" * sum((scale, s) in groups for s in ORDER)]
        for c, label, _ in KPIS:
            cells = []
            for s in ORDER:
                if (scale, s) not in groups:
                    continue
                r = next(x for x in summary if x["scale"] == scale and x["strategy"] == s)
                cv = next(x for x in comp if x["scale"] == scale and x["strategy"] == s)[f"{c}_pct_vs_S0"]
                m, sd = r[f"{c}_mean"], r[f"{c}_std"]
                cells.append(f"{m} ± {sd}" + ("" if s == "S0_fixed_time" or cv is None else f" ({cv:+.1f} %)"))
            md.append(f"| {label} | " + " | ".join(cells) + " |")
        md.append("")
    md += ["Valeurs : moyenne ± écart-type sur 3 graines ; (%) = écart relatif à S0. "
           "Avec 3 graines, un écart inférieur à environ 2 écarts-types n'est pas considéré comme significatif.", ""]
    outs["RESULTS"].write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
