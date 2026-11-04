"""Strategy comparison v2 (P2 of the 2026-10-12 mission) - SIMULATED results only (SUMO, LuST demand, Kirchberg 4 signals).

Reads output/experiments_v2/runs (produced with the current code: safety monitor on, patch p1) and
output/experiments_v1/runs (reference). Writes, without overwriting, in output/experiments_v2/results/:
  reproduction_v1_vs_v2_<tag>.csv   seeds 1-3: every KPI of v2 compared with v1 (same strategy/scale/seed)
  kpi_summary_v2_<tag>.csv          mean / sd per strategy, scale and seed set (dev = 1-3, fresh = 61-65, all)
  paired_v2_<tag>.csv               paired differences on the FRESH seeds 61-65 (never used for any design choice)
  safety_v2_<tag>.csv               signal-safety monitor totals per strategy
  RESULTS_v2_<tag>.md               readable summary

Paired differences: same seed = same demand realisation for both strategies; mean of the 5 per-seed
differences with a Student t 95 % interval (t(0.975, 4) = 2.776); "wins" = seeds where B < A.

    python scripts/simulation/analyze_strategies_v2.py --tag a
"""
import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sumo" / "lust_4_intersections" / "output"
V1, V2 = OUT / "experiments_v1" / "runs", OUT / "experiments_v2" / "runs"
RES = OUT / "experiments_v2" / "results"
ORDER = ["S0_fixed_time", "S1_actuated", "S2_demand_gap", "S2F_forecast_gap", "S2b_max_pressure", "S3_rl_qlearning"]
KPIS = ["avg_travel_time_s", "avg_waiting_time_s", "avg_time_loss_s", "avg_queue_veh", "max_queue_veh", "arrived",
        "avg_depart_delay_s", "co2_kg", "fuel_kg", "nox_g", "teleports", "collisions"]
DEV, FRESH = (1, 2, 3), (61, 62, 63, 64, 65)
T975 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}
PAIRS = [("S0_fixed_time", s) for s in ORDER[1:]] + [("S1_actuated", "S2_demand_gap"), ("S1_actuated", "S3_rl_qlearning"),
                                                      ("S2_demand_gap", "S3_rl_qlearning"), ("S2_demand_gap", "S2F_forecast_gap")]
ORIGIN = "SIMULATED_sumo_lust_kirchberg_4tls"


def load(folder):
    runs = {}
    for f in sorted(folder.glob("*/kpis.json")):
        n = f.parent.name
        if any(x in n for x in ("INCOMPLETE", "incident", "noforecast", "_ev")):
            continue
        k = json.loads(f.read_text(encoding="utf-8"))
        runs[(k["strategy"], float(k["scale"]), int(k["seed"]))] = k
    return runs


def write(name, rows):
    f = RES / name
    if f.exists():
        sys.exit(f"{f} exists - use another --tag")
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="a")
    p.add_argument("--experiments", default="v2", help="read output/experiments_<this>/runs (v2b = after the 2026-10-12 fixes)")
    a = p.parse_args(argv)
    global V2, RES
    V2 = OUT / f"experiments_{a.experiments}" / "runs"
    RES = OUT / f"experiments_{a.experiments}" / "results"
    RES.mkdir(parents=True, exist_ok=True)
    v1, v2 = load(V1), load(V2)
    scales = sorted({k[1] for k in v2})

    # 1. reproduction
    repro = []
    for key in sorted(v2):
        if key[2] in DEV and key in v1:
            diffs = {c: abs((v2[key].get(c) or 0) - (v1[key].get(c) or 0)) for c in KPIS}
            repro.append({"strategy": key[0], "scale": key[1], "seed": key[2], "max_abs_diff": round(max(diffs.values()), 6),
                          "travel_v1": v1[key]["avg_travel_time_s"], "travel_v2": v2[key]["avg_travel_time_s"],
                          "identical": max(diffs.values()) < 1e-9, "data_origin": ORIGIN})
    missing_v1 = sorted(k for k in v2 if k[2] in DEV and k not in v1)

    # 2. summary per seed set
    summary = []
    for sc in scales:
        for s in ORDER:
            for setname, seeds in (("dev_1-3", DEV), ("fresh_61-65", FRESH), ("all", DEV + FRESH)):
                rs = [v2[(s, sc, sd)] for sd in seeds if (s, sc, sd) in v2]
                if not rs:
                    continue
                row = {"scale": sc, "strategy": s, "seeds": setname, "n": len(rs)}
                for c in KPIS:
                    vals = [r[c] for r in rs if r.get(c) is not None]
                    row[c] = round(st.mean(vals), 3) if vals else None
                    row[c + "_sd"] = round(st.stdev(vals), 3) if len(vals) > 1 else 0.0
                row["data_origin"] = ORIGIN
                summary.append(row)

    # 3. paired comparisons on fresh seeds
    paired = []
    for sc in scales:
        for A, B in PAIRS:
            for c in ("avg_travel_time_s", "avg_waiting_time_s", "avg_time_loss_s", "avg_queue_veh", "co2_kg", "arrived"):
                d = [v2[(B, sc, sd)][c] - v2[(A, sc, sd)][c] for sd in FRESH if (A, sc, sd) in v2 and (B, sc, sd) in v2]
                if len(d) < 2:
                    continue
                m, sd_ = st.mean(d), st.stdev(d)
                half = T975[len(d) - 1] * sd_ / len(d) ** 0.5
                base = st.mean(v2[(A, sc, x)][c] for x in FRESH if (A, sc, x) in v2)
                lower_better = c != "arrived"
                paired.append({"scale": sc, "A": A, "B": B, "kpi": c, "n_seeds": len(d), "mean_A": round(base, 3),
                               "diff_B_minus_A": round(m, 3), "diff_pct": round(100 * m / base, 2) if base else None,
                               "ci95_low": round(m - half, 3), "ci95_high": round(m + half, 3),
                               "B_better_on_seeds": sum((x < 0) if lower_better else (x > 0) for x in d),
                               "significant_95": (m + half < 0 or m - half > 0), "data_origin": ORIGIN})

    # 4. safety + RL controller stats
    safety = []
    for s in ORDER:
        rs = [k for key, k in v2.items() if key[0] == s]
        sf = [k.get("safety") or {} for k in rs]
        row = {"strategy": s, "runs": len(rs), "runs_with_monitor": sum(bool(x) for x in sf),
               "transitions_checked": sum(x.get("transitions_checked", 0) for x in sf),
               "total_violations": sum(x.get("total_violations", 0) for x in sf)}
        for v in ("state_in_program", "green_to_red_without_yellow", "min_green", "yellow_duration", "max_green"):
            row[v] = sum((x.get("violations") or {}).get(v, 0) for x in sf)
        row["collisions"] = sum(k.get("collisions") or 0 for k in rs)
        row["teleports"] = sum(k.get("teleports") or 0 for k in rs)
        ctl = [k.get("controller") or {} for k in rs]
        dec = sum(c.get("decisions", 0) for c in ctl)
        row["controller_decisions"] = dec
        row["rl_fallback_share"] = round(sum(c.get("fallback_decisions", 0) for c in ctl) / dec, 3) if s == "S3_rl_qlearning" and dec else ""
        row["rl_updates_during_eval"] = sum(c.get("updates", 0) for c in ctl) if s == "S3_rl_qlearning" else ""
        row["rl_explorations_during_eval"] = sum(c.get("explorations", 0) for c in ctl) if s == "S3_rl_qlearning" else ""
        row["data_origin"] = ORIGIN
        safety.append(row)

    for name, rows in ((f"reproduction_v1_vs_v2_{a.tag}.csv", repro), (f"kpi_summary_v2_{a.tag}.csv", summary),
                       (f"paired_v2_{a.tag}.csv", paired), (f"safety_v2_{a.tag}.csv", safety)):
        write(name, rows)

    # markdown
    md = [f"# Comparaison des stratégies – experiments_{a.experiments} ({a.tag}) – résultats SIMULÉS", "",
          "Source : SUMO 1.27.1, demande LuST 07:00–08:00, réseau réduit Kirchberg 4 feux. **Aucune donnée réelle de trafic "
          "n'est utilisée par les contrôleurs ; aucun résultat ici n'est un résultat de trafic réel.**", "",
          f"Runs v2 complets : {len(v2)} (6 stratégies × échelles {', '.join(f'x{s:g}' for s in scales)} × graines 1–3 et 61–65).", "",
          "## 1. Reproduction de v1 (graines 1–3)", "",
          f"{sum(r['identical'] for r in repro)} / {len(repro)} runs identiques à v1 sur les {len(KPIS)} indicateurs "
          f"(écart absolu max. {max((r['max_abs_diff'] for r in repro), default=0)}). Runs v2 sans équivalent v1 : {len(missing_v1)}.", ""]
    for sc in scales:
        md += [f"## 2. Résultats x{sc:g} – graines neuves 61–65 (jamais utilisées pour un choix de conception)", "",
               "| Stratégie | Trajet (s) | Attente (s) | Temps perdu (s) | File moy. (véh.) | CO₂ (kg) | Arrivés |", "|---|---|---|---|---|---|---|"]
        for r in summary:
            if r["scale"] == sc and r["seeds"] == "fresh_61-65":
                md.append(f"| {r['strategy']} | {r['avg_travel_time_s']:.1f} ± {r['avg_travel_time_s_sd']:.1f} | {r['avg_waiting_time_s']:.1f} | "
                          f"{r['avg_time_loss_s']:.1f} | {r['avg_queue_veh']:.2f} | {r['co2_kg']:.1f} | {r['arrived']:.0f} |")
        md += ["", "Différences appariées (B − A) sur le temps de trajet moyen, IC 95 % de Student sur 5 graines :", "",
               "| A | B | Δ (s) | Δ % | IC 95 % | B meilleur sur | Significatif |", "|---|---|---|---|---|---|---|"]
        for r in paired:
            if r["scale"] == sc and r["kpi"] == "avg_travel_time_s":
                md.append(f"| {r['A']} | {r['B']} | {r['diff_B_minus_A']:+.2f} | {r['diff_pct']:+.1f} % | [{r['ci95_low']:+.2f} ; {r['ci95_high']:+.2f}] | "
                          f"{r['B_better_on_seeds']}/{r['n_seeds']} | {'oui' if r['significant_95'] else 'non'} |")
        md.append("")
    md += ["## 3. Sécurité des feux (moniteur indépendant, tous les runs de ce dossier)", "",
           "| Stratégie | Runs | Transitions vérifiées | Violations | Collisions | Téléportations | Repli RL |", "|---|---|---|---|---|---|---|"]
    for r in safety:
        md.append(f"| {r['strategy']} | {r['runs']} | {r['transitions_checked']} | {r['total_violations']} | {r['collisions']} | {r['teleports']} | "
                  f"{r['rl_fallback_share']} |")
    md += ["", "Règles vérifiées à chaque pas : état présent dans le programme du feu, pas de passage vert→rouge sans jaune, "
           "vert ≥ 5 s, jaune et tout-rouge à leur durée programmée (dépassement signalé dès qu'il se produit), vert ≤ 90 s. "
           "Conflits de mouvements : les contrôleurs ne fabriquent jamais d'état, ils ne choisissent que des phases des programmes "
           "LuST ; ces programmes ont été vérifiés avec la matrice de conflits de SUMO "
           "(`scripts/simulation/check_signal_conflicts_v1.py`, 48 phases, 0 conflit prioritaire, voir output/safety/).", ""]
    f = RES / f"RESULTS_v2_{a.tag}.md"
    if f.exists():
        sys.exit(f"{f} exists")
    f.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
