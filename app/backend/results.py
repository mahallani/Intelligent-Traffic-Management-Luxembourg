"""Read-only access to the experiment results, comparisons, CSV exports, reports and data sources."""
from __future__ import annotations

import csv
import io
import json
import statistics as st
from pathlib import Path

from agents.common.sim_env import PROJECT_ROOT, SCENARIO_DIR

OUTPUT = SCENARIO_DIR / "output"
RUN_FILES = ("kpis.json", "queue_timeseries.csv", "decisions.csv", "alerts.csv", "predictions.csv")
# 2026-10-22: final evaluation set (seeds 1-3 and 61-65, 8 runs per strategy and demand) instead of v1 (seeds 1-3)
EVAL_DIR = OUTPUT / "experiments_v2b" / "runs"
KPIS = [("avg_travel_time_s", "Temps de trajet moyen (s)", -1), ("avg_waiting_time_s", "Attente moyenne (s)", -1),
        ("avg_time_loss_s", "Temps perdu moyen (s)", -1), ("avg_queue_veh", "File moyenne (véh. arrêtés)", -1),
        ("max_queue_veh", "File maximale (véh.)", -1), ("arrived", "Véhicules arrivés", 1),
        ("avg_depart_delay_s", "Retard d'entrée moyen (s)", -1), ("co2_kg", "CO2 simulé (kg)", -1),
        ("nox_g", "NOx simulé (g)", -1), ("fuel_kg", "Carburant simulé (kg)", -1)]
EXPORT_COLS = ["run_id", "source", "strategy", "scale", "seed", "backend", "stopped_early"] + [k for k, _, _ in KPIS] + \
              ["completed_trips", "unfinished_trips_at_end", "teleports", "collisions", "data_origin"]
STRATEGY_LABELS = {"S0_fixed_time": "S0 – temps fixe LuST", "S1_actuated": "S1 – feux actuated SUMO",
                   "S2_demand_gap": "S2 – règle demande / creux", "S2F_forecast_gap": "S2F – S2 + prévision en cascade",
                   "S2b_max_pressure": "S2b – max-pressure", "S3_rl_qlearning": "S3 – agent RL (Q-learning)"}
REPORTS = ["FINAL_DEMO_REPORT.md", "AGENT_EVALUATION_REPORT.md", "APPLICATION_GUIDE.md", "CASCADE_PREDICTION_AUDIT.md",
           "PROJECT_GAP_ANALYSIS.md", "DATA_VALIDATION_REPORT.md",
           "sumo/lust_4_intersections/output/experiments_v1/results/RESULTS_v1.md",
           "sumo/lust_4_intersections/output/experiments_v1/results/DEMO_REPORT_v1.md",
           "data/reports/DATA_READINESS_REPORT.md", "data/reports/readiness_by_objective_v1.md", "agents/README.md"]


class NotFound(LookupError):
    pass


def _source(rel: str) -> str:
    if rel.startswith("app_runs/"):
        return "application"
    if rel.startswith("experiments_v1/runs/") or rel.startswith("experiments_v2b/runs/"):
        return "évaluation"
    if rel.startswith("experiments_demo"):
        return "démo"
    return "autre"


def list_runs() -> list[dict]:
    runs = []
    for k in sorted(OUTPUT.glob("**/kpis.json")):
        rel = str(k.parent.relative_to(OUTPUT)).replace("\\", "/")
        if "INCOMPLETE" in rel or "/training" in rel or "prediction_data" in rel or "detection" in rel:
            continue
        try:
            d = json.loads(k.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"id": rel, "name": k.parent.name, "source": _source(rel), "strategy": d.get("strategy"),
                     "scale": d.get("scale"), "seed": d.get("seed"), "stopped_early": d.get("stopped_early", False),
                     **{c: d.get(c) for c, _, _ in KPIS}, "files": [f for f in RUN_FILES if (k.parent / f).exists()],
                     "data_origin": d.get("data_origin")})
    return runs


def run_path(run_id: str) -> Path:
    p = (OUTPUT / run_id).resolve()
    if OUTPUT.resolve() not in p.parents or not (p / "kpis.json").exists():
        raise NotFound(f"unknown run {run_id}")
    return p


def run_file(run_id: str, name: str) -> Path:
    if name not in RUN_FILES:
        raise NotFound(f"file not available: {name}")
    f = run_path(run_id) / name
    if not f.exists():
        raise NotFound(f"{name} not produced by this run")
    return f


def export_csv() -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLS, delimiter=";", extrasaction="ignore")
    w.writeheader()
    for r in list_runs():
        d = json.loads((OUTPUT / r["id"] / "kpis.json").read_text(encoding="utf-8"))
        w.writerow({**d, "run_id": r["id"], "source": r["source"]})
    return buf.getvalue()


def _eval_runs(strategy: str, scale: float) -> list[dict]:
    out = []
    for d in sorted(EVAL_DIR.glob(f"{strategy}_x{scale:g}_seed*")):
        name = d.name
        if any(x in name for x in ("incident", "INCOMPLETE", "noforecast")) or not (d / "kpis.json").exists():
            continue
        out.append(json.loads((d / "kpis.json").read_text(encoding="utf-8")))
    return out


def compare(a: str, b: str, scale: float) -> dict:
    ra, rb = _eval_runs(a, scale), _eval_runs(b, scale)
    if not ra or not rb:
        raise NotFound(f"no evaluation runs for {a if not ra else b} at demand x{scale:g}")
    rows = []
    for k, label, direction in KPIS:
        va = [r[k] for r in ra if r.get(k) is not None]
        vb = [r[k] for r in rb if r.get(k) is not None]
        if not va or not vb:
            continue
        ma, mb = st.mean(va), st.mean(vb)
        sa = st.stdev(va) if len(va) > 1 else 0.0
        sb = st.stdev(vb) if len(vb) > 1 else 0.0
        pct = 100 * (mb - ma) / ma if ma else None
        if len(va) < 2 or len(vb) < 2 or abs(mb - ma) <= 2 * max(sa, sb):
            verdict = "non significatif"
        else:
            verdict = "meilleur" if (mb - ma) * direction > 0 else "moins bon"
        rows.append({"kpi": k, "label": label, "a_mean": round(ma, 2), "a_std": round(sa, 2), "b_mean": round(mb, 2),
                     "b_std": round(sb, 2), "pct": None if pct is None else round(pct, 1), "verdict": verdict})
    return {"scale": scale, "a": {"id": a, "label": STRATEGY_LABELS.get(a, a), "n": len(ra), "seeds": sorted(r["seed"] for r in ra)},
            "b": {"id": b, "label": STRATEGY_LABELS.get(b, b), "n": len(rb), "seeds": sorted(r["seed"] for r in rb)},
            "rows": rows, "rule": "significant when |B - A| > 2 x the larger standard deviation over seeds",
            "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls"}


def reports() -> list[str]:
    return [r for r in REPORTS if (PROJECT_ROOT / r).exists()]


def report_text(name: str) -> str:
    if name not in REPORTS or not (PROJECT_ROOT / name).exists():
        raise NotFound(f"unknown report {name}")
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def data_sources() -> dict:
    sources = [
        {"name": "CITA – capteurs autoroutiers", "origin": "réelle",
         "description": "Vitesse, occupation et débit des capteurs DATEX II des autoroutes luxembourgeoises.",
         "period": "3 instants de mesure (07/10 et 10/10/2026), 247 capteurs ; collecte de 7 jours non démarrée.",
         "use": "Aucun capteur dans la zone des 4 feux : non utilisé par la simulation ni par les agents."},
        {"name": "CITA – événements", "origin": "réelle",
         "description": "Chantiers, pannes et obstructions publiés par CITA (identifiants DATEX).",
         "period": "24 événements sur 2 instantanés, aucun accident.",
         "use": "Insuffisant pour entraîner une détection d'incidents réelle."},
        {"name": "PCH – comptages 2025", "origin": "réelle",
         "description": "Comptages horaires de 272 postes nationaux (véhicules/heure).",
         "period": "01/01 – 31/12/2025.",
         "use": "Comparaison d'ordre de grandeur avec LuST autour de la zone ; calibration par facteur global : échec documenté."},
        {"name": "GTFS – transports publics", "origin": "réelle",
         "description": "Horaire planifié des bus et du tram (lignes, arrêts, horaires).",
         "period": "30/09 – 12/12/2026.",
         "use": "Contrôle de compatibilité : 3 arrêts sur 18 proches d'un arrêt LuST, tram absent du réseau SUMO."},
        {"name": "LuST + simulations du projet", "origin": "simulée",
         "description": "Réseau et demande synthétiques LuST (vers 2015), scénario réduit de 4 feux, runs des agents.",
         "period": "Journée type, fenêtre 07:00–08:00.",
         "use": "Seule source des résultats affichés dans l'application (indicateurs, décisions, détections, prévisions)."},
    ]
    readiness = {}
    f = PROJECT_ROOT / "data" / "reports" / "readiness_by_objective_v1.json"
    labels = {"A": "Détection d'incidents sur données réelles", "B": "Prévision sur données réelles",
              "C": "Simulation SUMO / RL", "D": "Indicateurs d'impact"}
    if f.exists():
        r = json.loads(f.read_text(encoding="utf-8"))["readiness"]
        readiness = {k: {"label": labels.get(k, k), "verdict": v["verdict"]} for k, v in r.items()}
    return {"sources": sources, "readiness": readiness}
