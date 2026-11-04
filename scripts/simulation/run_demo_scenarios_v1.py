"""Reproducible demo scenarios for the Design-Thinking prototype presentation (2026-10-22). SIMULATED only.

A - Congestion: S0 (fixed time) vs S3 (Q-learning agent), demand x5, the SAME seeds 61-65 for both.
B - Blocked lane: lane -31070#4_1 (approach of Carrefour 4) slowed to 0.05 m/s from 07:20 to 07:40, demand x5,
    seeds 61-63, S0 and S3, each run WITH and WITHOUT the incident (same seed), plus one S3 run with an ambulance
    (priority on / off) during the incident. Measured from the output files only: alerts.csv, decisions.csv,
    queue_timeseries.csv, kpis.json.

Runs go to sumo/lust_4_intersections/output/demo_scenarios_v1/{A,B}/<run>/ (a finished run is skipped, so the
script can be re-run until everything is done). Summaries (never overwritten): demo_scenarios_v1/summary_<tag>.*

    python scripts/simulation/run_demo_scenarios_v1.py --run A
    python scripts/simulation/run_demo_scenarios_v1.py --run B
    python scripts/simulation/run_demo_scenarios_v1.py --summarize --tag a
Re-run on another machine (e.g. Windows) into a separate folder, then compare the two summaries:
    python scripts/simulation/run_demo_scenarios_v1.py --run A --outdir demo_scenarios_v1_windows
    python scripts/simulation/run_demo_scenarios_v1.py --run B --outdir demo_scenarios_v1_windows --summarize --tag win
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.orchestrator import Incident, make_controller, run_episode  # noqa: E402

OUT = ROOT / "sumo" / "lust_4_intersections" / "output" / "demo_scenarios_v1"
QTABLE = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "rl" / "qtable_v4_FROZEN_ep26_eval.json"
LANE, TLS, T0, T1 = "-31070#4_1", "-29958", 26400.0, 27600.0
A_SEEDS, B_SEEDS, SCALE = (61, 62, 63, 64, 65), (61, 62, 63), 5.0
T975 = {2: 4.303, 3: 3.182, 4: 2.776}


def ctrl(strategy):
    return make_controller(strategy, qtable=QTABLE) if strategy.startswith("S3") else make_controller(strategy)


def one(group, name, strategy, seed, **kw):
    out = OUT / group / name
    if (out / "kpis.json").exists():
        return
    run_episode(strategy, SCALE, seed, out, controller=ctrl(strategy), detection_mode="discharge", **kw)
    print("done", group, name, flush=True)


def run_a():
    for s in ("S0_fixed_time", "S3_rl_qlearning"):
        for seed in A_SEEDS:
            one("A", f"{s}_x5_seed{seed}", s, seed)


def run_b():
    for s in ("S0_fixed_time", "S3_rl_qlearning"):
        for seed in B_SEEDS:
            one("B", f"{s}_x5_seed{seed}_no_incident", s, seed)
            one("B", f"{s}_x5_seed{seed}_incident", s, seed, incident=Incident(LANE, T0, T1))
    for prio in (False, True):
        one("B", f"S3_rl_qlearning_x5_seed61_incident_ambulance{'_prio' if prio else ''}", "S3_rl_qlearning", 61,
            incident=Incident(LANE, T0, T1), emergency_at=T0, emergency_priority=prio)


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def k(p):
    return json.loads((p / "kpis.json").read_text(encoding="utf-8"))


def ci(d):
    m = st.mean(d)
    h = T975[len(d) - 1] * st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else 0.0
    return m, m - h, m + h


def summarize(tag):
    lines, rows = [f"# Scénarios de démonstration ({tag}) – résultats SIMULÉS (SUMO, demande LuST ×5)", ""], []
    # ---- A
    A = OUT / "A"
    K = [("avg_travel_time_s", "Temps de trajet moyen (s)"), ("avg_waiting_time_s", "Attente moyenne (s)"),
         ("avg_queue_veh", "File moyenne (véh.)"), ("max_queue_veh", "File maximale (véh.)"), ("co2_kg", "CO2 simulé (kg)"),
         ("arrived", "Véhicules arrivés")]
    lines += ["## A. Congestion : S0 (temps fixe) contre S3 (agent RL), mêmes graines 61-65", "",
              "| Indicateur | S0 | S3 | Différence S3 − S0 | IC 95 % | S3 meilleur sur |", "|---|---|---|---|---|---|"]
    for key, lab in K:
        a = [k(A / f"S0_fixed_time_x5_seed{s}")[key] for s in A_SEEDS]
        b = [k(A / f"S3_rl_qlearning_x5_seed{s}")[key] for s in A_SEEDS]
        d = [y - x for x, y in zip(a, b)]
        m, lo, hi = ci(d)
        better = sum((x > 0) if key == "arrived" else (x < 0) for x in d)
        lines.append(f"| {lab} | {st.mean(a):.2f} | {st.mean(b):.2f} | {m:+.2f} ({100 * m / st.mean(a):+.1f} %) | [{lo:+.2f} ; {hi:+.2f}] | {better}/5 |")
        rows.append({"scenario": "A", "kpi": key, "S0_mean": round(st.mean(a), 3), "S3_mean": round(st.mean(b), 3),
                     "diff": round(m, 3), "ci_low": round(lo, 3), "ci_high": round(hi, 3), "S3_better_seeds": better,
                     "data_origin": DATA_ORIGIN})
    s3 = [k(A / f"S3_rl_qlearning_x5_seed{s}")["controller"] for s in A_SEEDS]
    fb = sum(c["fallback_decisions"] for c in s3) / sum(c["decisions"] for c in s3)
    saf = sum(k(A / f"{x}_x5_seed{s}")["safety"]["total_violations"] for x in ("S0_fixed_time", "S3_rl_qlearning") for s in A_SEEDS)
    lines += ["", f"Part des décisions de S3 prises par la règle de secours S2 : {100 * fb:.1f} %. Violations de sécurité (10 runs) : {saf}.", ""]
    # ---- B
    B = OUT / "B"
    lines += ["## B. Voie bloquée avant le Carrefour 4 (07:20-07:40), même graine avec et sans incident", "",
              "| Stratégie | Graine | Détecté | Délai (s) | Alertes sur la voie | Fausses alertes ailleurs | Arrêtés Carrefour 4 pendant l'incident (sans → avec) | Trajet moyen (sans → avec, s) | Décisions de l'agent au Carrefour 4 pendant l'incident (sans → avec) |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in ("S0_fixed_time", "S3_rl_qlearning"):
        for seed in B_SEEDS:
            ni, wi = B / f"{s}_x5_seed{seed}_no_incident", B / f"{s}_x5_seed{seed}_incident"
            kn, kw = k(ni), k(wi)
            al = [a for a in rd(wi / "alerts.csv") if float(a["raised_s"]) >= 25500]
            on = [a for a in al if a["lane"].rsplit("_", 1)[0] == LANE.rsplit("_", 1)[0] and T0 <= float(a["raised_s"]) <= T1 + 60]
            off = len(al) - len(on)

            def halt(run):
                q = [float(r[f"halting_{TLS}"]) for r in rd(run / "queue_timeseries.csv") if T0 <= float(r["time_s"]) < T1]
                return sum(q) / len(q)

            def ndec(run):
                return sum(1 for r in rd(run / "decisions.csv") if r["tls"] == TLS and T0 <= float(r["time_s"]) < T1
                           and r["reason"] == "agent_decision")
            inc = kw.get("incident", {})
            lines.append(f"| {s} | {seed} | {'oui' if inc.get('detected') else 'non'} | {inc.get('detection_delay_s', '–')} | {len(on)} | {off} | "
                         f"{halt(ni):.1f} → {halt(wi):.1f} | {kn['avg_travel_time_s']} → {kw['avg_travel_time_s']} | "
                         f"{ndec(ni) if s.startswith('S3') else '– (programme fixe)'} → {ndec(wi) if s.startswith('S3') else '–'} |")
            rows.append({"scenario": "B", "kpi": f"{s}_seed{seed}", "S0_mean": "", "S3_mean": "", "diff": "", "ci_low": "", "ci_high": "",
                         "S3_better_seeds": "", "detected": inc.get("detected"), "delay_s": inc.get("detection_delay_s"),
                         "alerts_on_lane": len(on), "alerts_elsewhere": off, "halting_tls4_no": round(halt(ni), 2),
                         "halting_tls4_inc": round(halt(wi), 2), "travel_no": kn["avg_travel_time_s"], "travel_inc": kw["avg_travel_time_s"],
                         "data_origin": DATA_ORIGIN})
    lines += ["", "Aucune stratégie ne reçoit les alertes : S3 réagit seulement parce que ses observations (files) changent.", ""]
    amb = []
    for prio in (False, True):
        r = B / f"S3_rl_qlearning_x5_seed61_incident_ambulance{'_prio' if prio else ''}"
        e = k(r)["emergency"]
        amb.append(f"| {'avec' if prio else 'sans'} | {e.get('travel_time_s')} | {e.get('waiting_time_s')} | {k(r)['safety']['total_violations']} |")
    lines += ["### Ambulance pendant l'incident (S3, graine 61)", "", "| Priorité urgence | Trajet ambulance (s) | Attente ambulance (s) | Violations |",
              "|---|---|---|---|"] + amb + ["", "Source : fichiers kpis.json, alerts.csv, decisions.csv, queue_timeseries.csv des runs de demo_scenarios_v1."]
    md, cs = OUT / f"summary_{tag}.md", OUT / f"summary_{tag}.csv"
    for f in (md, cs):
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    keys = sorted({x for r in rows for x in r}, key=lambda x: (x != "scenario", x))
    with open(cs, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lines))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", choices=["A", "B"])
    p.add_argument("--summarize", action="store_true")
    p.add_argument("--tag", default="a")
    p.add_argument("--outdir", default="demo_scenarios_v1",
                   help="folder under sumo/lust_4_intersections/output (e.g. demo_scenarios_v1_windows to rerun on Windows)")
    a = p.parse_args()
    OUT = OUT.parent / a.outdir
    if a.run == "A":
        run_a()
    elif a.run == "B":
        run_b()
    if a.summarize:
        summarize(a.tag)
