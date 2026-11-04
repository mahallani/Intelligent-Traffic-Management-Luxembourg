"""Faithful decision explanations (SIMULATED, 2026-10-22): for phase changes at one traffic light, print what the
controller recorded at decision time (decisions.csv 'explanation' column) next to the halted-vehicle count at that
light just before and after (queue_timeseries.csv, sampled every 5 s). Before/after values are observations, NOT the
causal effect of the decision (the counterfactual is not simulated).

    python scripts/simulation/make_xai_examples_v1.py --run B/S3_rl_qlearning_x5_seed61_incident --tls -29958 \
        --t0 26400 --t1 26800 --tag a
Writes demo_scenarios_v1/xai_examples_<tag>.md (never overwritten).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sumo" / "lust_4_intersections" / "output" / "demo_scenarios_v1"
QCLS = ["0", "1-2", "3-5", "6-10", ">10"]
MCLS = ["0", "1-2", "3-5", ">5"]
TCLS = ["<=10 s", "11-20 s", "21-40 s", ">40 s"]


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def hms(t):
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def text(ex):
    s = ex.get("source", "")
    if s.startswith("sécurité"):
        return f"Règle de sécurité : vert de {ex['vert_s']:.0f} s = limite {ex['limite_s']:.0f} s → passage forcé"
    si = ex.get("situation", {})
    obs = (f"phase verte n°{si.get('phase_verte')}, arrêtés côté vert {QCLS[int(si['file_servie'])]}, "
           f"en attente ailleurs {QCLS[int(si['file_autre'])]}, en mouvement {MCLS[int(si['en_mouvement'])]}, "
           f"vert depuis {TCLS[int(si['durée_vert'])]}") if si else ""
    if s == "table apprise":
        gap = ex["q_passer"] - ex["q_garder"]
        return (f"Agent RL, table apprise. Observé : {obs}. Q(passer)={ex['q_passer']:.2f} > Q(garder)={ex['q_garder']:.2f} "
                f"(écart {gap:.3f}{' : quasi-égalité' if gap < 0.1 else ''}); visites garder/passer = {ex['visites_garder_passer']}")
    if s.startswith("règle de secours"):
        r = ex["règle_S2"]
        return (f"Agent RL → {s}. Observé : {obs}. Règle S2 : arrêtés au vert {r['arrêtés_vert']} ≤ {r['seuils'][0]}, "
                f"en mouvement {r['en_mouvement_vert']} ≤ {r['seuils'][1]}, en attente ailleurs {r['attente_autre_phase']} → passer")
    return json.dumps(ex, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--tls", default="-29958")
    ap.add_argument("--t0", type=float, default=26400)
    ap.add_argument("--t1", type=float, default=26800)
    ap.add_argument("--tag", default="a")
    a = ap.parse_args()
    md = OUT / f"xai_examples_{a.tag}.md"
    if md.exists():
        sys.exit(f"{md} exists - use another --tag")
    run = OUT / a.run
    q = rd(run / "queue_timeseries.csv")
    ts = [float(r["time_s"]) for r in q]

    def halt(t):
        i = min(max(bisect.bisect_right(ts, t) - 1, 0), len(q) - 1)
        return q[i][f"halting_{a.tls}"]
    L = [f"# Explications fidèles – {a.run}, feu {a.tls}, {hms(a.t0)}-{hms(a.t1)} (SIMULÉ)", "",
         "Texte construit uniquement à partir de la colonne `explanation` de decisions.csv. Arrêtés au feu : queue_timeseries.csv. "
         "Avant/après = observation, pas un effet causal.", "",
         "| Heure | Phase → | Vert (s) | Explication enregistrée | Arrêtés au feu t−10 s / t / t+30 s / t+60 s |", "|---|---|---|---|---|"]
    for r in rd(run / "decisions.csv"):
        t = float(r["time_s"])
        if r["tls"] != a.tls or not (a.t0 <= t < a.t1):
            continue
        ex = json.loads(r["explanation"]) if r["explanation"] else {}
        L.append(f"| {hms(t)} | {r['from_phase']} → {r['to_phase']} | {float(r['green_duration_s']):.0f} | {text(ex)} | "
                 f"{halt(t - 10)} / {halt(t)} / {halt(t + 30)} / {halt(t + 60)} |")
    L += ["", "Seuls les changements de phase sont journalisés : les décisions « garder » ne le sont pas."]
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
