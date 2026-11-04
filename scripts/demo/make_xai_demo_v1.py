"""XAI demo (2026-10-22): faithful explanation of REAL decisions of a traffic-signal agent, read from a run folder.

What it reads (nothing else): <run>/decisions.csv (column 'explanation' = what the controller recorded at decision
time: observed classes, Q-values, visit counts, fallback rule inputs, or the safety rule), <run>/queue_timeseries.csv
(halted vehicles per signal, every 5 s) and <run>/kpis.json (run settings).

What it writes, in a NEW folder (refuses to overwrite):
  faithfulness_check.json  - every logged decision checked against the controller's own rules (see check())
  xai_demo.png             - one slide (16:9): 3 consecutive decisions at one signal + halted vehicles around them
  xai_demo.md              - the same decisions in text, provenance and limits

    python scripts/demo/make_xai_demo_v1.py --run sumo/lust_4_intersections/output/app_runs/<run> \
        --tls=-29958 --times 26921 26931 26941 --out docs/xai_demo_v1
Before/after halted counts are OBSERVATIONS, not the causal effect of a decision (no counterfactual is simulated).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

Q_EDGES, M_EDGES = (0, 2, 5, 10), (0, 2, 5)          # = agents/decision/controllers.py (QLearningController)
QCLS = ["0", "1–2", "3–5", "6–10", "> 10"]
MCLS = ["0", "1–2", "3–5", "> 5"]
TCLS = ["≤ 10 s", "11–20 s", "21–40 s", "> 40 s"]
LABELS = {"-28692": "Carrefour 1", "-23354": "Carrefour 2", "-20484": "Carrefour 3", "-29958": "Carrefour 4"}
MIN_VISITS = 3


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x <= e:
            return i
    return len(edges)


def hms(t):
    t = int(round(float(t)))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def check(rows):
    """Faithfulness: the recorded explanation must agree with the rule that really produced the action."""
    res = {"rows": len(rows), "missing_explanation": 0, "learned": 0, "fallback": 0, "safety": 0, "other": 0, "violations": []}
    for r in rows:
        if not r.get("explanation"):
            res["missing_explanation"] += 1
            continue
        e, t = json.loads(r["explanation"]), r["time_s"]
        src = e.get("source", "")
        if r["reason"] == "max_green":
            res["safety"] += 1
            if not (src.startswith("sécurité") and e["vert_s"] >= e["limite_s"] - 1e-6 and abs(float(r["green_duration_s"]) - e["vert_s"]) < 1e-6):
                res["violations"].append((t, r["tls"], "safety rule not met"))
            continue
        if e.get("action") != "passer":                       # only phase changes are logged
            res["violations"].append((t, r["tls"], "logged change but action != passer"))
        if src == "table apprise":
            res["learned"] += 1
            v = e["visites_garder_passer"]
            if not (min(v) >= MIN_VISITS and e["q_passer"] > e["q_garder"]):
                res["violations"].append((t, r["tls"], "learned: not argmax or too few visits"))
        elif src.startswith("règle de secours"):
            res["fallback"] += 1
            v, s2, si = e["visites_garder_passer"], e["règle_S2"], e["situation"]
            if e["q_garder"] is not None and min(v) >= MIN_VISITS and e["q_garder"] != e["q_passer"]:
                res["violations"].append((t, r["tls"], "fallback used although the table was trusted"))
            if not (s2["arrêtés_vert"] <= s2["seuils"][0] and s2["en_mouvement_vert"] <= s2["seuils"][1] and s2["attente_autre_phase"] > 0):
                res["violations"].append((t, r["tls"], "S2 rule not met"))
            # two independent records of the same observation must agree (raw S2 counts vs RL classes)
            if (int(si["file_servie"]), int(si["file_autre"]), int(si["en_mouvement"])) != \
               (_bin(s2["arrêtés_vert"], Q_EDGES), _bin(s2["attente_autre_phase"], Q_EDGES), _bin(s2["en_mouvement_vert"], M_EDGES)):
                res["violations"].append((t, r["tls"], "classes disagree with raw counts"))
        else:
            res["other"] += 1
    res["violations_count"] = len(res["violations"])
    return res


def card_lines(e):
    """(chip, colour, observed lines, reason lines) built ONLY from the recorded explanation."""
    src = e.get("source", "")
    if src.startswith("sécurité"):
        return "Règle de sécurité", "#5d6b7a", [f"Vert depuis {e['vert_s']:.0f} s"], [f"Limite {e['limite_s']:.0f} s atteinte → passage forcé"]
    si = e["situation"]
    obs = [f"Arrêtés sur la voie au vert : {QCLS[int(si['file_servie'])]}",
           f"En mouvement au vert : {MCLS[int(si['en_mouvement'])]}",
           f"Attente sur une autre phase : {QCLS[int(si['file_autre'])]}",
           f"Vert depuis : {TCLS[int(si['durée_vert'])]}"]
    if src == "table apprise":
        gap = e["q_passer"] - e["q_garder"]
        strength = "préférence nette" if gap >= 1.0 else ("préférence faible" if gap >= 0.1 else "quasi-égalité")
        reason = [f"Table apprise : « passer » coûte moins ({strength})",
                  f"Situation déjà vue {e['visites_garder_passer'][0]} fois (garder) / {e['visites_garder_passer'][1]} fois (passer)"]
        return "Agent RL – table apprise", "#18a6b8", obs, reason
    s2 = e["règle_S2"]
    v = e["visites_garder_passer"]
    obs = [f"Arrêtés sur la voie au vert : {s2['arrêtés_vert']}",
           f"En mouvement au vert : {s2['en_mouvement_vert']}",
           f"Attente sur une autre phase : {s2['attente_autre_phase']}",
           f"Vert depuis : {TCLS[int(si['durée_vert'])]}"]
    reason = [f"Table non fiable ici (vue {v[0]} / {v[1]} fois, minimum {MIN_VISITS})",
              f"→ règle S2 : ≤ {s2['seuils'][0]} arrêté, ≤ {s2['seuils'][1]} en mouvement, attente ailleurs"]
    return "Règle de secours S2", "#e8742a", obs, reason


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--tls", default="-29958")
    ap.add_argument("--times", nargs="+", type=float, required=True)
    ap.add_argument("--out", default="docs/xai_demo_v1", type=Path)
    ap.add_argument("--run-label", default=None, help="text shown as provenance (default: run folder name)")
    a = ap.parse_args()
    if a.out.exists():
        sys.exit(f"{a.out} exists - choose another --out")
    rows = rd(a.run / "decisions.csv")
    q = rd(a.run / "queue_timeseries.csv")
    k = json.loads((a.run / "kpis.json").read_text(encoding="utf-8"))
    chk = check(rows)
    sel = [r for r in rows if r["tls"] == a.tls and float(r["time_s"]) in set(a.times)]
    if len(sel) != len(a.times):
        sys.exit(f"found {len(sel)} of {len(a.times)} decisions at {a.tls}")
    label = a.run_label or a.run.name
    a.out.mkdir(parents=True)
    (a.out / "faithfulness_check.json").write_text(json.dumps({"run": label, **chk}, ensure_ascii=False, indent=1), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    NAVY, INK, MUTED, RULE = "#0f2a3d", "#1d2b3a", "#5d6b7a", "#cfd6de"
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor="white")
    fig.text(0.04, 0.93, f"Pourquoi l'agent a changé le feu du {LABELS.get(a.tls, a.tls)} ?", fontsize=26, weight="bold", color=NAVY)
    fig.text(0.04, 0.885, f"Trois décisions réelles consécutives · {k['strategy']} · demande ×{k['scale']:g} · graine {k['seed']} · "
             f"backend {k['backend']} · données SIMULÉES (SUMO)", fontsize=12.5, color=MUTED)
    W, X0 = 0.29, 0.04
    for i, r in enumerate(sorted(sel, key=lambda r: float(r["time_s"]))):
        e = json.loads(r["explanation"])
        chip, col, obs, reason = card_lines(e)
        x = X0 + i * (W + 0.025)
        ax = fig.add_axes([x, 0.36, W, 0.48])
        ax.set_axis_off()
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.03", fc="white", ec=RULE, lw=1.4, transform=ax.transAxes))
        ax.add_patch(FancyBboxPatch((0, 0.9), 1, 0.1, boxstyle="square,pad=0", fc=col, ec=col, transform=ax.transAxes))
        ax.text(0.04, 0.95, f"{chr(65 + i)}  {hms(r['time_s'])}   {chip}", fontsize=13.5, weight="bold", color="white", va="center", transform=ax.transAxes)
        ax.text(0.04, 0.84, "Observé par l'agent", fontsize=11, weight="bold", color=INK, transform=ax.transAxes)
        for j, line in enumerate(obs):
            ax.text(0.06, 0.77 - j * 0.065, line, fontsize=11, color=INK, transform=ax.transAxes)
        ax.text(0.04, 0.47, "Raison enregistrée", fontsize=11, weight="bold", color=INK, transform=ax.transAxes)
        for j, line in enumerate(reason):
            ax.text(0.06, 0.40 - j * 0.065, line, fontsize=10.5, color=INK, transform=ax.transAxes, wrap=True)
        if e.get("q_garder") is not None:                      # learned values (cost of the future halted vehicles)
            bx = fig.add_axes([x + 0.035, 0.385, W - 0.06, 0.085])
            vals = [-e["q_garder"], -e["q_passer"]]
            trusted = e.get("source") == "table apprise"
            bars = bx.barh(["garder", "passer"], vals, color=[RULE, col if trusted else RULE], height=0.6)
            bx.invert_yaxis()
            for b, v in zip(bars, vals):
                bx.text(b.get_width(), b.get_y() + b.get_height() / 2, f" {v:.2f}", va="center", fontsize=9.5, color=INK)
            bx.set_xlim(0, max(vals) * 1.35 if max(vals) > 0 else 1)
            bx.tick_params(labelsize=9.5, colors=MUTED, length=0)
            bx.set_xticks([])
            for s in bx.spines.values():
                s.set_visible(False)
            bx.set_title("Coût futur estimé (– valeur Q)" + ("" if trusted else " – non utilisé"), fontsize=9.5, color=MUTED, loc="left", pad=2)
        ax.text(0.04, 0.03, f"→ Passer à la phase suivante ({r['from_phase']} → {r['to_phase']}, vert tenu {float(r['green_duration_s']):.0f} s)",
                fontsize=10.5, weight="bold", color=NAVY, transform=ax.transAxes)
    # halted vehicles around the decisions
    t0, t1 = min(a.times) - 90, max(a.times) + 90
    ts = [(float(r["time_s"]), float(r[f"halting_{a.tls}"])) for r in q if t0 <= float(r["time_s"]) <= t1]
    lx = fig.add_axes([0.06, 0.1, 0.9, 0.19])
    lx.plot([t for t, _ in ts], [v for _, v in ts], color=NAVY, lw=2)
    lx.fill_between([t for t, _ in ts], [v for _, v in ts], color=NAVY, alpha=0.08)
    for i, t in enumerate(sorted(a.times)):
        lx.axvline(t, color="#e8742a" if i == 1 else "#18a6b8", lw=1.5, ls="--")
        lx.text(t, lx.get_ylim()[1] * 0.92 if lx.get_ylim()[1] else 1, f" {chr(65 + i)}", color=INK, fontsize=12, weight="bold")
    ticks = [t for t in range(int(t0) // 30 * 30, int(t1) + 1, 30) if t >= t0]
    lx.set_xticks(ticks, [hms(t) for t in ticks])
    lx.tick_params(labelsize=9.5, colors=MUTED)
    for s in ("top", "right"):
        lx.spines[s].set_visible(False)
    lx.set_ylabel("véh. arrêtés", fontsize=10, color=MUTED)
    lx.set_title(f"Véhicules arrêtés au {LABELS.get(a.tls, a.tls)} (relevés toutes les 5 s) – observation, pas l'effet causal d'une décision",
                 fontsize=10.5, color=MUTED, loc="left")
    fig.text(0.04, 0.035, f"Source : {label}/decisions.csv (colonne « explanation », écrite par le contrôleur au moment de la décision) et queue_timeseries.csv.",
             fontsize=9, color=MUTED)
    fig.text(0.04, 0.012, f"Contrôle de fidélité sur tout le run : {chk['rows']} décisions journalisées, {chk['missing_explanation']} sans explication, "
             f"{chk['violations_count']} incohérence(s). Q = estimation apprise en simulation ; les décisions « garder » ne sont pas journalisées.",
             fontsize=9, color=MUTED)
    fig.savefig(a.out / "xai_demo.png", facecolor="white")

    L = [f"# Démo XAI – décisions réelles au {LABELS.get(a.tls, a.tls)} (SIMULÉ)", "",
         f"Run : `{label}` – {k['strategy']}, demande ×{k['scale']:g}, graine {k['seed']}, backend {k['backend']}.", "",
         "| | Heure | Source | Observé | Raison enregistrée | Action |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(sorted(sel, key=lambda r: float(r["time_s"]))):
        e = json.loads(r["explanation"])
        chip, _c, obs, reason = card_lines(e)
        qtxt = f" Q(garder)={e['q_garder']}, Q(passer)={e['q_passer']}." if e.get("q_garder") is not None else ""
        L.append(f"| {chr(65 + i)} | {hms(r['time_s'])} | {chip} | {'; '.join(obs)} | {' '.join(reason)}{qtxt} | phase {r['from_phase']} → {r['to_phase']} |")
    L += ["", f"Contrôle de fidélité sur tout le run : {chk['rows']} décisions journalisées, {chk['missing_explanation']} sans explication, "
          f"{chk['learned']} table apprise, {chk['fallback']} règle de secours, {chk['safety']} sécurité, {chk['violations_count']} incohérence(s).",
          "", "Q = somme actualisée estimée de –(véhicules arrêtés sur toutes les entrées du feu)/10 par relevé de 5 s : plus proche de 0 = moins d'attente prévue.",
          "Limites : seuls les changements de phase sont journalisés (pas les décisions « garder ») ; l'agent RL voit des classes, pas les nombres exacts ; "
          "les courbes avant/après sont des observations, pas un effet causal ; aucune explication pour le modèle de prévision."]
    (a.out / "xai_demo.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
