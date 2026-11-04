"""Captures (images) of the SUMO datasets used by the models - report docs/sumo_datasets_v1 (added 2026-10-16).

Reads ONLY existing files (scenario inputs, simulation runs, models, results) and writes PNG images plus
stats.json into a NEW folder docs/sumo_datasets_v1/ (refuses to run if it already exists). Every number shown
comes from the files. All data shown are SIMULATED (SUMO + LuST demand) unless stated otherwise.

    python scripts/simulation/make_dataset_captures_v1.py
"""
from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.prediction.cascade import FEATURES, HORIZONS, episode_samples  # noqa: E402

SC = ROOT / "sumo" / "lust_4_intersections"
OUT = SC / "output"
E1, E2 = OUT / "experiments_v1", OUT / "experiments_v2b"
DST = ROOT / "docs" / "sumo_datasets_v1"
TLS = ["-28692", "-23354", "-20484", "-29958"]
TLS_NAME = {t: f"Carrefour {i + 1}" for i, t in enumerate(TLS)}
STRAT = ["S0_fixed_time", "S1_actuated", "S2_demand_gap", "S2F_forecast_gap", "S2b_max_pressure", "S3_rl_qlearning"]
SLAB = {"S0_fixed_time": "S0 temps fixe", "S1_actuated": "S1 actuated", "S2_demand_gap": "S2 règle",
        "S2F_forecast_gap": "S2F + prévision", "S2b_max_pressure": "S2b max-pressure", "S3_rl_qlearning": "S3 RL"}
SCOL = dict(zip(STRAT, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]))
INK, INK2, GRID, SURF = "#1b2430", "#5a6472", "#e3e6ea", "#ffffff"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
                     "axes.titlelocation": "left", "axes.titlesize": 11})
STATS: dict = {}


def clock(t):
    t = int(float(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def read_csv(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def save(fig, name):
    fig.savefig(DST / name, dpi=130, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)
    print("wrote", name, flush=True)


def table_png(name, header, rows, col_w=None, title=None, source=None):
    """A 'capture' of a file extract: monospaced table, header shaded."""
    n = len(rows)
    col_w = col_w or [1.0] * len(header)
    width = max(6.0, sum(col_w) * 1.05)
    fig = plt.figure(figsize=(width, 0.32 * (n + 1) + (0.55 if title else 0.15) + (0.3 if source else 0)))
    ax = fig.add_axes([0, 0.06 if source else 0, 1, 0.88 if title else 1])
    ax.axis("off")
    tb = ax.table(cellText=[[str(c) for c in r] for r in rows], colLabels=header, loc="upper left",
                  colWidths=[w / sum(col_w) for w in col_w], cellLoc="left")
    tb.auto_set_font_size(False)
    tb.set_fontsize(8.5)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_height(1.0 / (n + 1.6))
        cell.get_text().set_fontfamily("DejaVu Sans Mono")
        if r == 0:
            cell.set_facecolor("#eef2f6")
            cell.get_text().set_color(INK)
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor(SURF if r % 2 else "#fafbfc")
            cell.get_text().set_color(INK)
    if title:
        fig.suptitle(title, x=0.005, ha="left", fontsize=11, fontweight="bold", color=INK, y=0.995)
    if source:
        fig.text(0.005, 0.005, source, fontsize=7.5, color=INK2, family="DejaVu Sans Mono")
    save(fig, name)


# ----------------------------------------------------------------------------------------------- 1. scenario
def scenario():
    import sumolib
    net = sumolib.net.readNet(str(SC / "net" / "kirchberg_4tls.net.xml"), withPrograms=True)
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    n_lanes = 0
    for e in net.getEdges():
        for ln in e.getLanes():
            xs, ys = zip(*ln.getShape())
            ax.plot(xs, ys, color="#b9c2cc", lw=1.4, solid_capstyle="round", zorder=1)
            n_lanes += 1
    for t in TLS:
        tl = net.getTLS(t)
        pts = [c[0].getShape()[-1] for c in tl.getConnections()]
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        ax.scatter([x], [y], s=150, color=INK, zorder=3, edgecolor=SURF, linewidth=2)
        ax.annotate(f"{TLS_NAME[t]}\nfeu {t}", (x, y), xytext=(10, -4), textcoords="offset points", fontsize=9,
                    color=INK, fontweight="bold", zorder=4)
    ax.set_aspect("equal")
    ax.set_title("Réseau routier simulé : avenue J.F. Kennedy, Kirchberg (fichier net/kirchberg_4tls.net.xml)")
    save(fig, "01_reseau.png")
    progs = []
    for t in TLS:
        for p in net.getTLS(t).getPrograms().values():
            for i, ph in enumerate(p.getPhases()):
                progs.append([TLS_NAME[t], t, p._id, i, f"{ph.duration:g}", ph.state])
    p0 = [r for r in progs if r[2] == "0"]
    STATS["scenario"] = {"edges": len(net.getEdges()), "lanes": n_lanes, "nodes": len(net.getNodes()),
                         "tls_phases_program0": len(p0),
                         "cycle_s": {t: sum(float(r[4]) for r in p0 if r[1] == t) for t in TLS}}
    table_png("03_programmes_feux.png", ["Carrefour", "Feu", "Prog.", "Phase", "Durée (s)", "État des mouvements (G/g vert, y jaune, r rouge)"],
              [r for r in p0], [1.1, 0.8, 0.5, 0.5, 0.8, 3.2],
              "Programmes de feux LuST d'origine (programme « 0 », utilisé par S0 et comme base des agents)",
              "source : sumo/lust_4_intersections/net/kirchberg_4tls.net.xml")
    # demand
    root = ET.parse(SC / "routes" / "kirchberg_0700_0800.rou.xml").getroot()
    vehs = [v for v in root.iter("vehicle")] + [v for v in root.iter("trip")]
    types = Counter(v.get("type", "?") for v in vehs)
    mins = Counter(int((float(v.get("depart")) - 25200) // 60) for v in vehs if v.get("depart", "").replace(".", "").isdigit())
    fig, ax = plt.subplots(figsize=(9, 3.2))
    xs = list(range(0, 61))
    ax.bar([x + 0.5 for x in xs], [mins.get(x, 0) for x in xs], width=0.82, color="#2a78d6")
    ax.set_xlim(0, 61)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60], ["07:00", "07:10", "07:20", "07:30", "07:40", "07:50", "08:00"])
    ax.set_ylabel("véhicules / minute")
    ax.set_title(f"Demande LuST ×1 : départs par minute ({len(vehs)} véhicules, fichier routes/kirchberg_0700_0800.rou.xml)")
    save(fig, "02_demande.png")
    rows = []
    for v in vehs[:12]:
        r = v.find("route")
        edges = (r.get("edges") if r is not None else v.get("route", "")) or ""
        e = edges.split()
        rows.append([v.get("id"), v.get("type", ""), clock(v.get("depart")), len(e), e[0] if e else "", e[-1] if e else ""])
    table_png("04_routes_extrait.png", ["id véhicule", "type", "départ", "nb routes", "1re route", "dernière route"], rows,
              [1.6, 1.3, 0.8, 0.8, 1.2, 1.2], "Extrait de la demande : un véhicule = une heure de départ + un itinéraire",
              "source : sumo/lust_4_intersections/routes/kirchberg_0700_0800.rou.xml (12 premiers véhicules)")
    STATS["demand"] = {"vehicles_x1": len(vehs), "types": dict(types.most_common()), "max_per_min": max(mins.values())}


# --------------------------------------------------------------------------------------- 2. one run, all files
def run_files():
    run = E1 / "prediction_data" / "train" / "S0_fixed_time_x5_seed201"
    q = read_csv(run / "queue_timeseries.csv")
    sel = [r for r in q if 26400 <= float(r["time_s"]) < 26460][:12]
    cols = ["time_s", "halting_total", "queue_m_total", "vehicles_in_network"] + [f"halting_{t}" for t in TLS]
    table_png("05_queue_timeseries_extrait.png", ["heure"] + cols + ["data_origin"],
              [[clock(r["time_s"])] + [r[c] for c in cols] + ["SIMULATED_…"] for r in sel],
              [0.8, 0.7, 1.0, 1.0, 1.3, 1.25, 1.25, 1.25, 1.25, 1.1],
              "queue_timeseries.csv : l'état des files toutes les 5 s (fichier principal des modèles)",
              f"source : {run.relative_to(ROOT).as_posix()}/queue_timeseries.csv (07:20:00-07:21:00, {len(q)} lignes au total)")
    STATS["run_example"] = {"run": run.name, "queue_rows": len(q), "queue_cols": list(q[0].keys())}
    # tripinfo
    root = ET.parse(run / "tripinfo.xml").getroot()
    trips = list(root.iter("tripinfo"))
    rows = []
    for t in trips[:12]:
        em = t.find("emissions")
        rows.append([t.get("id"), clock(t.get("depart")), clock(t.get("arrival")) if float(t.get("arrival", -1)) > 0 else "—",
                     t.get("duration"), t.get("waitingTime"), t.get("timeLoss"), t.get("routeLength"),
                     f"{float(em.get('CO2_abs')) / 1000:.1f}" if em is not None else ""])
    table_png("07_tripinfo_extrait.png", ["id véhicule", "départ", "arrivée", "durée (s)", "attente (s)", "temps perdu (s)",
                                         "distance (m)", "CO2 (g)"], rows, [1.6, 0.8, 0.8, 0.8, 0.8, 1.0, 0.9, 0.8],
              "tripinfo.xml : une ligne par véhicule (source des indicateurs finaux)",
              f"source : {run.relative_to(ROOT).as_posix()}/tripinfo.xml ({len(trips)} trajets)")
    # kpis
    k = json.loads((run / "kpis.json").read_text(encoding="utf-8"))
    keys = ["strategy", "scale", "seed", "backend", "inserted", "arrived", "avg_travel_time_s", "avg_waiting_time_s",
            "avg_time_loss_s", "avg_queue_veh", "max_queue_veh", "co2_kg", "teleports", "collisions", "data_origin"]
    table_png("08_kpis_extrait.png", ["clé", "valeur"], [[x, k.get(x)] for x in keys], [1.6, 2.6],
              "kpis.json : le résumé chiffré d'une simulation", f"source : {run.relative_to(ROOT).as_posix()}/kpis.json")
    # decisions + predictions from an RL evaluation run
    r3 = E2 / "runs" / "S3_rl_qlearning_x5_seed61"
    d = read_csv(r3 / "decisions.csv")
    sel = [r for r in d if float(r["time_s"]) >= 26400][:12]
    table_png("06_decisions_extrait.png", ["heure", "feu", "phase avant", "phase après", "durée du vert (s)", "raison", "contrôleur"],
              [[clock(r["time_s"]), r["tls"], r["from_phase"], r["to_phase"], r["green_duration_s"], r["reason"], r["controller"]] for r in sel],
              [0.8, 0.8, 0.9, 0.9, 1.2, 1.2, 1.4], "decisions.csv : chaque changement de feu décidé par l'agent",
              f"source : {r3.relative_to(ROOT).as_posix()}/decisions.csv ({len(d)} décisions)")
    p = read_csv(r3 / "predictions.csv")
    sel = [r for r in p if float(r["origin_s"]) >= 26400][:12]
    table_png("09_predictions_extrait.png", ["prévu à", "pour", "feu", "horizon (min)", "prévision", "observé", "erreur",
                                            "persistance", "erreur persist."],
              [[clock(r["origin_s"]), clock(r["target_s"]), r["tls"], r["horizon_min"], r["forecast"], r["observed"], r["error"],
                r["persistence"], r["error_persistence"]] for r in sel], [0.8, 0.8, 0.8, 0.9, 0.9, 0.8, 0.8, 0.9, 1.0],
              "predictions.csv : chaque prévision, puis la valeur réellement observée",
              f"source : {r3.relative_to(ROOT).as_posix()}/predictions.csv ({len(p)} lignes)")


# ------------------------------------------------------------------------------------ 3. prediction datasets
def split_runs(split):
    out = []
    for d in sorted((E1 / "prediction_data" / split).iterdir()):
        if d.is_dir() and "INCOMPLETE" not in d.name and (d / "kpis.json").exists():
            k = json.loads((d / "kpis.json").read_text(encoding="utf-8"))
            out.append((k["strategy"], float(k["scale"]), int(k["seed"]), d))
    return out


def prediction():
    splits = {s: split_runs(s) for s in ("train", "test", "holdout")}
    fig, axes = plt.subplots(1, 3, figsize=(11, 2.6))
    labels = {"train": "Entraînement", "test": "Test", "holdout": "Contrôle final"}
    st_info = {}
    for ax, (s, runs) in zip(axes, splits.items()):
        strats = [x for x in STRAT if any(r[0] == x for r in runs)]
        scales = sorted({r[1] for r in runs})
        seeds = sorted({r[2] for r in runs})
        ax.set_xlim(0, len(scales))
        ax.set_ylim(0, len(strats))
        ax.grid(False)
        for i, stg in enumerate(strats):
            for j, scv in enumerate(scales):
                n = sum(1 for r in runs if r[0] == stg and r[1] == scv)
                ax.add_patch(plt.Rectangle((j + 0.05, len(strats) - i - 0.95), 0.9, 0.9,
                                           color=SCOL[stg] if n else "#f1f3f5", alpha=0.85 if n else 1))
                ax.text(j + 0.5, len(strats) - i - 0.5, str(n) if n else "", ha="center", va="center", color=SURF,
                        fontweight="bold")
        ax.set_xticks([j + 0.5 for j in range(len(scales))], [f"×{v:g}" for v in scales])
        ax.set_yticks([len(strats) - i - 0.5 for i in range(len(strats))], [SLAB[x] for x in strats])
        ax.set_title(f"{labels[s]} : {len(runs)} runs, graines {', '.join(map(str, seeds))}", fontsize=10)
        for sp in ax.spines.values():
            sp.set_visible(False)
        st_info[s] = {"runs": len(runs), "seeds": seeds, "scales": scales, "strategies": strats}
    fig.suptitle("Découpage des simulations pour la prédiction (nombre de runs par stratégie et demande)", x=0.005, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    save(fig, "10_decoupage_prediction.png")
    # samples
    for s, runs in splits.items():
        n = 0
        for (_st, _sc, _se, d) in runs:
            n += len(episode_samples(read_csv(d / "queue_timeseries.csv")))
        st_info[s]["examples"] = n
    STATS["prediction_splits"] = st_info
    # curves
    fig, ax = plt.subplots(figsize=(9, 3.4))
    for scv, col in ((1.0, "#2a78d6"), (3.0, "#1baf7a"), (5.0, "#eb6834")):
        d = E1 / "prediction_data" / "train" / f"S0_fixed_time_x{scv:g}_seed201"
        q = read_csv(d / "queue_timeseries.csv")
        mins = {}
        for r in q:
            mins.setdefault(int((float(r["time_s"]) - 25200) // 60), []).append(float(r["halting_total"]))
        xs = sorted(mins)
        ys = [sum(mins[x]) / len(mins[x]) for x in xs]
        ax.plot(xs, ys, color=col, lw=2, label=f"demande ×{scv:g}")
        ax.annotate(f"×{scv:g}", (xs[-1], ys[-1]), xytext=(4, 0), textcoords="offset points", color=INK, fontsize=9)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60], ["07:00", "07:10", "07:20", "07:30", "07:40", "07:50", "08:00"])
    ax.set_ylabel("véhicules arrêtés (4 feux)")
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Ce que contient un run : véhicules arrêtés aux 4 feux, moyenne par minute (S0, graine 201)")
    save(fig, "11_courbes_files.png")
    # one learning example
    d = E1 / "prediction_data" / "train" / "S0_fixed_time_x5_seed201"
    smp = [x for x in episode_samples(read_csv(d / "queue_timeseries.csv")) if x["origin"] == 26400.0 and x["tls"] == "-28692"][0]
    desc = {"own_now": "arrêtés à ce feu, minute actuelle", "own_5min_ago": "arrêtés à ce feu, 5 min avant",
            "own_trend": "tendance (maintenant - 5 min avant)", "neighbours_now": "arrêtés aux feux voisins",
            "total_now": "arrêtés aux 4 feux", "vehicles_now": "véhicules dans la zone", "tau": "heure (fraction depuis 07:00)",
            "bias": "constante"}
    rows = [["ENTRÉE", f, f"{v:.2f}".rstrip("0").rstrip("."), desc.get(f, "indicateur du feu (1 = ce feu)")]
            for f, v in zip(FEATURES, smp["x"])]
    rows += [["À PRÉDIRE", f"+{h // 60} min", f"{smp['y'][h]:.2f}", f"arrêtés à ce feu à {clock(26400 + h)}"] for h in HORIZONS]
    table_png("12_exemple_apprentissage.png", ["rôle", "variable", "valeur", "signification"], rows, [1.0, 1.3, 0.7, 2.6],
              f"Un exemple d'apprentissage : feu -28692 (Carrefour 1) à 07:20, run {d.name}",
              "calculé par agents/prediction/cascade.py (episode_samples) à partir de queue_timeseries.csv")
    # holdout metrics
    m = [r for r in read_csv(E1 / "prediction" / "cascade_metrics_holdout_v1.csv") if r["group"] == "all_holdout"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    w = 0.26
    for i, (key, lab, col) in enumerate((("MAE_cascade", "modèle en cascade", "#2a78d6"),
                                         ("MAE_persistence", "persistance (rien ne change)", "#eb6834"),
                                         ("MAE_profile", "moyenne historique", "#1baf7a"))):
        xs = [j + (i - 1) * (w + 0.02) for j in range(len(m))]
        vals = [float(r[key]) for r in m]
        ax.bar(xs, vals, width=w, color=col, label=lab)
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.05, f"{v:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(m)), [f"+{r['horizon_min']} min" for r in m])
    ax.set_ylabel("erreur moyenne (véhicules)")
    ax.legend(frameon=False, ncols=3, loc="upper left", bbox_to_anchor=(0, -0.12))
    ax.set_title(f"Contrôle final (graines jamais vues) : erreur de prévision, {m[0]['n']} prévisions par horizon")
    save(fig, "13_erreurs_prediction.png")
    STATS["holdout"] = [{k: r[k] for k in ("horizon_min", "n", "episodes", "MAE_cascade", "MAE_persistence", "MAE_profile")} for r in m]


# ------------------------------------------------------------------------------------------------- 4. RL
def rl():
    log = read_csv(E1 / "rl" / "training_log_v4.csv")
    ep = [int(r["episode"]) for r in log]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)
    a1.plot(ep, [float(r["avg_travel_time_s"]) for r in log], color="#6250d6", lw=2, marker="o", ms=4)
    a1.set_ylabel("trajet moyen (s)")
    a1.set_title("Entraînement de l'agent RL : 26 épisodes SUMO, demande ×5 (graines 101-126)")
    a2.plot(ep, [100 * float(r["fallback_decisions"]) / float(r["decisions"]) for r in log], color="#eb6834", lw=2, marker="o", ms=4)
    a2.set_ylabel("% décisions par la règle S2")
    a2.set_xlabel("épisode")
    save(fig, "14_entrainement_rl.png")
    STATS["rl"] = {"episodes": len(log), "first": log[0], "last": log[-1]}
    d = json.loads((E1 / "rl" / "qtable_v4_FROZEN_ep26_eval.json").read_text(encoding="utf-8"))
    q, n = d["q"], d.get("n", {})
    top = sorted(q, key=lambda s: -sum(n.get(s, [0, 0])))[:12]
    rows = []
    for s in top:
        tid, g, qc, qo, mc, te = s.split("|")
        vis = n.get(s, [0, 0])
        trusted = min(vis) >= 3 and q[s][0] != q[s][1]
        best = "garder" if q[s][0] > q[s][1] else "passer"
        rows.append([tid, g, qc, qo, mc, te, f"{q[s][0]:.3f}", f"{q[s][1]:.3f}", f"{vis[0]}/{vis[1]}",
                     best if trusted else "règle S2"])
    table_png("15_table_q_extrait.png", ["feu", "phase", "file servie", "file autre", "en mouvement", "durée vert",
                                         "Q garder", "Q passer", "visites G/P", "décision"], rows,
              [0.8, 0.6, 0.8, 0.8, 0.9, 0.8, 0.8, 0.8, 0.9, 0.9],
              "Table apprise par l'agent RL : 12 situations les plus vues (classes 0 = faible … 3 = forte)",
              f"source : experiments_v1/rl/qtable_v4_FROZEN_ep26_eval.json ({len(q)} situations vues)")
    STATS["qtable"] = {"states": len(q), "trusted": sum(1 for s in q if min(n.get(s, [0, 0])) >= 3 and q[s][0] != q[s][1])}


# -------------------------------------------------------------------------------------------- 5. evaluation
def evaluation():
    summ = [r for r in read_csv(E2 / "results" / "kpi_summary_v2_b.csv") if r["seeds"] == "fresh_61-65"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), sharey=True)
    for ax, sc in zip(axes, ("1.0", "5.0")):
        rs = sorted([r for r in summ if r["scale"] == sc], key=lambda r: STRAT.index(r["strategy"]))
        ys = list(range(len(rs)))[::-1]
        v = [float(r["avg_travel_time_s"]) for r in rs]
        e = [float(r["avg_travel_time_s_sd"]) for r in rs]
        ax.barh(ys, v, xerr=e, color=[SCOL[r["strategy"]] for r in rs], height=0.62, error_kw={"ecolor": INK2, "lw": 1})
        for y, val in zip(ys, v):
            ax.text(val + 2, y, f"{val:.1f}", va="center", fontsize=8.5, color=INK)
        ax.set_yticks(ys, [SLAB[r["strategy"]] for r in rs])
        ax.set_xlim(0, max(v) * 1.18)
        ax.set_title(f"demande ×{float(sc):g}", fontsize=10)
        ax.set_xlabel("temps de trajet moyen (s)")
        ax.grid(axis="y", visible=False)
    fig.suptitle("Évaluation finale (experiments_v2b) : graines 61-65 jamais utilisées, moyenne ± écart-type",
                 x=0.005, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    save(fig, "16_evaluation_strategies.png")
    STATS["evaluation"] = [{k: r[k] for k in ("scale", "strategy", "n", "avg_travel_time_s", "avg_travel_time_s_sd")} for r in summ]
    det = read_csv(E1 / "detection_v2" / "detection_v2_summary_v3.csv")
    keep = [r for r in det if r["variant"] in ("rules", "discharge", "rules_confirm_seeds11_12", "discharge_confirm_seeds11_12")]
    table_png("17_detection.png", ["variante", "demande", "runs", "incidents", "rappel", "précision", "F1", "fausses alertes/h",
                                   "délai (s)"],
              [[r["variant"], r["scale"], r["runs"], r["incidents"], r["recall"], r["precision"], r["F1"],
                r["false_alerts_per_hour"], r["mean_delay_s"]] for r in keep],
              [2.4, 0.7, 0.5, 0.7, 0.6, 0.7, 0.6, 1.1, 0.7],
              "Jeux de données de la détection : incidents simulés (voie ralentie 07:20-07:40)",
              "source : experiments_v1/detection_v2/detection_v2_summary_v3.csv")
    em = read_csv(E1 / "emergency_v2" / "emergency_summary_v2.csv")
    fig, ax = plt.subplots(figsize=(8, 3.2))
    strs = ["S0_fixed_time", "S1_actuated", "S2_demand_gap"]
    w = 0.36
    for i, (prio, lab, col) in enumerate((("False", "sans priorité", "#8a94a3"), ("True", "avec priorité", "#e34948"))):
        vals = []
        for s in strs:
            rs = [float(r["ambulance_travel_s"]) for r in em if r["strategy"] == s and r["priority"] == prio]
            vals.append(sum(rs) / len(rs))
        xs = [j + (i - 0.5) * (w + 0.03) for j in range(len(strs))]
        ax.bar(xs, vals, width=w, color=col, label=lab)
        for x, v in zip(xs, vals):
            ax.text(x, v + 3, f"{v:.0f}", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(strs)), [SLAB[s] for s in strs])
    ax.set_ylabel("trajet de l'ambulance (s)")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.12), ncols=2)
    ax.set_title("Jeux de données urgence : ambulance simulée à 07:20, ×5, graines 1-5 (moyenne)")
    save(fig, "18_urgence.png")


def inventory():
    groups = [("experiments_v1/prediction_data/train", "Entraîner la prédiction"),
              ("experiments_v1/prediction_data/test", "Tester la prédiction"),
              ("experiments_v1/prediction_data/holdout", "Contrôle final de la prédiction"),
              ("experiments_v1/rl/training_v4", "Entraîner l'agent RL"),
              ("experiments_v1/runs", "1re comparaison des stratégies"),
              ("experiments_v2b/runs", "Évaluation finale des stratégies"),
              ("experiments_v1/detection_v2/discharge", "Évaluer la détection"),
              ("experiments_v1/detection_v2/discharge_confirm_seeds11_12", "Confirmer la détection (graines neuves)"),
              ("experiments_v1/emergency_v2", "Évaluer la priorité urgence")]
    inv = []
    for rel, use in groups:
        p = OUT / rel
        runs = [d for d in p.iterdir() if d.is_dir() and "INCOMPLETE" not in d.name and (d / "kpis.json").exists()]
        inc = [d for d in p.iterdir() if d.is_dir() and "INCOMPLETE" in d.name]
        ks = [json.loads((d / "kpis.json").read_text(encoding="utf-8")) for d in runs]
        size = sum(f.stat().st_size for d in runs for f in d.iterdir() if f.is_file())
        inv.append({"folder": f"sumo/lust_4_intersections/output/{rel}", "use": use, "runs": len(runs), "incomplete_kept": len(inc),
                    "seeds": sorted({int(k["seed"]) for k in ks}), "scales": sorted({float(k["scale"]) for k in ks}),
                    "strategies": [s for s in STRAT if any(k["strategy"] == s for k in ks)], "size_mb": round(size / 1e6, 1)})
    STATS["inventory"] = inv


if __name__ == "__main__":
    if DST.exists():
        sys.exit(f"{DST} exists - choose another version")
    DST.mkdir(parents=True)
    inventory()
    scenario()
    run_files()
    prediction()
    rl()
    evaluation()
    (DST / "stats.json").write_text(json.dumps(STATS, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("done", DST)
