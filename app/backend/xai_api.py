"""XAI routes of the control application (2026-10-29): the REAL decisions of a run and their exact SHAP explanation.

    GET /api/xai/runs                       recorded runs of the application (folders of app_runs with decisions.csv)
    GET /api/xai/decisions?run=<name>       decisions of the current run (run omitted) or of a recorded run
    GET /api/xai/shap?index=<i>&run=<name>  exact SHAP explanation of decision <i>, computed on demand

Sources of decisions (nothing is invented):
  * current run, simulation active  -> the full in-memory log of the intervention agent (TLSActuator.log), the same
                                       rows that orchestrator.run_episode writes to decisions.csv at the end;
  * current run finished / stopped  -> its decisions.csv (complete), or the in-memory log if the file is not there;
  * recorded run                    -> its decisions.csv (folder name validated, never a free path).
Index i = position in that log; the log is append-only, so an index never changes during or after the run.

SHAP: only through agents/xai/shap_qtable.py (unchanged): check_learned_decision -> verify_logged_values against the
frozen Q-table -> exact_shapley_delta. A decision that is not taken by the learned table of S3 (other strategy,
fallback rule S2, safety rule "max green") gets a 422 answer with the reason, never SHAP values.
S0 and S1 log no decision at all: their phase changes are made by SUMO's own programs (fixed / actuated)."""
from __future__ import annotations

import csv
import json
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from agents.xai import shap_qtable as sx

from .network import LABELS as CARREFOURS

RUN_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,160}$")
CSV_FIELDS = ["time_s", "tls", "from_phase", "to_phase", "green_duration_s", "reason", "controller", "data_origin", "explanation"]
NO_DECISION_STRATEGIES = {
    "S0_fixed_time": "S0 (programmes fixes) : les changements de phase sont faits par les programmes LuST de SUMO ; "
                     "aucun agent ne décide, donc aucune décision n'est enregistrée ni explicable.",
    "S1_actuated": "S1 (feux adaptatifs SUMO) : les changements de phase sont décidés par la logique « actuated » "
                   "intégrée à SUMO ; l'application ne les pilote pas, donc aucune décision n'est enregistrée ni explicable.",
}
NOT_S3 = "Décision de la stratégie {s}, qui n'utilise pas la table Q-learning S3 : pas de valeurs SHAP pour elle."


def _clock(t: float) -> str:
    s = int(t)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


@lru_cache(maxsize=2)
def _table(path: str, mtime_ns: int) -> sx.QTable:
    return sx.load_qtable(Path(path))


def frozen_table() -> sx.QTable:
    p = sx.DEFAULT_QTABLE
    if not p.exists():
        raise HTTPException(503, f"table Q-learning introuvable : {sx._rel(p)}")
    return _table(str(p), p.stat().st_mtime_ns)


# ----------------------------------------------------------------------------------------------- rows
def row_from_log(entry, strategy: str) -> dict:
    """TLSActuator.log tuple -> the row that run_episode writes in decisions.csv (same fields, same JSON)."""
    ex = entry[6] if len(entry) > 6 else None
    return {"time_s": str(float(entry[0])), "tls": str(entry[1]), "from_phase": str(entry[2]), "to_phase": str(entry[3]),
            "green_duration_s": str(entry[4]), "reason": str(entry[5]), "controller": strategy or "",
            "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
            "explanation": json.dumps(ex, ensure_ascii=False) if ex else ""}


def read_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh, delimiter=";")]


def eligibility(row: dict) -> dict:
    """Same rule as shap_qtable.check_learned_decision (called, not copied); the reason is given in plain French."""
    r = dict(row)
    try:
        r["explanation_json"] = json.loads(r["explanation"]) if r.get("explanation") else None
    except json.JSONDecodeError:
        return {"eligible": False, "reason": "Explication enregistrée illisible (JSON invalide)."}
    ex = r["explanation_json"] or {}
    try:
        sx.check_learned_decision(r)
        return {"eligible": True, "reason": "Décision prise par la table Q-learning apprise (S3) : explication SHAP calculable."}
    except sx.ExplanationError as e:
        if r.get("controller") != "S3_rl_qlearning":
            msg = NOT_S3.format(s=r.get("controller") or "inconnue")
        elif r.get("reason") == "max_green":
            msg = ("Changement imposé par la règle de sécurité « vert maximum » "
                   f"({ex.get('vert_s', '?')} s, limite {ex.get('limite_s', '?')} s) : ce n'est pas une décision de la table.")
        elif str(ex.get("source", "")).startswith("règle de secours"):
            msg = (f"Décision prise par la {ex['source']} : la table n'était pas assez fiable dans cette situation "
                   "(chaque action doit avoir été essayée au moins 3 fois), donc pas de valeurs SHAP.")
        elif r.get("reason") != "agent_decision":
            msg = f"Changement de phase imposé par une règle ({r.get('reason')}), pas par la table."
        elif not r["explanation_json"]:
            msg = ("Ce run n'a pas enregistré l'explication de ses décisions (version antérieure au 22/10/2026) : "
                   "l'état observé est inconnu, donc aucune valeur SHAP ne peut être calculée.")
        else:
            msg = f"Décision non admissible au calcul SHAP : {e}"
        return {"eligible": False, "reason": msg}


def public_decision(i: int, row: dict) -> dict:
    t = float(row["time_s"])
    try:
        ex = json.loads(row["explanation"]) if row.get("explanation") else None
    except json.JSONDecodeError:
        ex = None
    return {"index": i, "time_s": t, "clock": _clock(t), "tls": row["tls"], "carrefour": CARREFOURS.get(row["tls"], row["tls"]),
            "from_phase": int(row["from_phase"]), "to_phase": int(row["to_phase"]),
            "green_duration_s": float(row["green_duration_s"]), "reason": row["reason"], "controller": row.get("controller", ""),
            "explanation": ex, "shap": eligibility(row)}


# ------------------------------------------------------------------------------------------- sources
def _run_dir(runs_dir: Path, name: str) -> Path:
    if not RUN_NAME.match(name or ""):
        raise HTTPException(400, "nom de run invalide")
    root = runs_dir.resolve()
    d = (runs_dir / name).resolve()
    if d.parent != root or not d.is_dir():
        raise HTTPException(404, f"run introuvable : {name}")
    return d


def _strategy_of(d: Path, rows: list[dict]) -> str | None:
    if rows and rows[0].get("controller"):
        return rows[0]["controller"]
    k = d / "kpis.json"
    if k.exists():
        try:
            return json.loads(k.read_text(encoding="utf-8")).get("strategy")
        except (OSError, json.JSONDecodeError):
            return None
    return None


def load_source(mgr, run: str | None) -> dict:
    """Decisions of the current run (run=None) or of a recorded run, with where they come from."""
    if run:
        d = _run_dir(mgr.runs_dir, run)
        f = d / "decisions.csv"
        if not f.exists():
            raise HTTPException(404, f"pas de decisions.csv dans le run {run}")
        rows = read_rows(f)
        return {"mode": "recorded", "run": d.name, "status": "finished" if (d / "kpis.json").exists() else "incomplete",
                "strategy": _strategy_of(d, rows), "source": "decisions.csv", "run_dir": d, "rows": rows}
    snap = mgr.decision_snapshot()
    if snap["status"] in (None, "idle") or snap["run_dir"] is None:
        return {"mode": "current", "run": None, "status": "idle", "strategy": None, "source": None, "run_dir": None, "rows": []}
    d = Path(snap["run_dir"])
    f = d / "decisions.csv"
    if not snap["active"] and f.exists():
        rows = read_rows(f)
        source = "decisions.csv"
    else:
        rows = [row_from_log(e, snap["strategy"]) for e in snap["log"]]
        source = "mémoire (simulation en cours)" if snap["active"] else "mémoire"
    return {"mode": "current", "run": d.name, "status": snap["status"], "strategy": snap["strategy"], "source": source,
            "run_dir": d, "rows": rows}


def explain(row: dict, run_dir: Path | None, from_file: bool) -> dict:
    """Exact SHAP through shap_qtable.explain_logged_decision. A decision still in memory is written alone to a
    temporary decisions.csv with exactly the format of run_episode, so the engine and its checks are the same."""
    table_path = sx.DEFAULT_QTABLE
    frozen_table()            # clear 503 if the table is missing
    t, tls = float(row["time_s"]), row["tls"]
    if from_file and run_dir is not None:
        res = sx.explain_logged_decision(run_dir=run_dir, tls=tls, time_s=t, qtable_path=table_path)
    else:
        with tempfile.TemporaryDirectory(prefix="xai_live_") as tmp:
            with open(Path(tmp) / "decisions.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, delimiter=";")
                w.writeheader()
                w.writerow({k: row.get(k, "") for k in CSV_FIELDS})
            res = sx.explain_logged_decision(run_dir=Path(tmp), tls=tls, time_s=t, qtable_path=table_path)
    res["decision"]["run"] = run_dir.name if run_dir is not None else None
    return res


# ---------------------------------------------------------------------------------------------- routes
def make_router(mgr) -> APIRouter:
    r = APIRouter(prefix="/api/xai")

    @r.get("/runs")
    def runs():
        out = []
        root = Path(mgr.runs_dir)
        if root.exists():
            for d in sorted((p for p in root.iterdir() if p.is_dir() and (p / "decisions.csv").exists()),
                            key=lambda p: p.name, reverse=True):
                try:
                    rows = read_rows(d / "decisions.csv")
                except (OSError, csv.Error):
                    continue
                out.append({"run": d.name, "strategy": _strategy_of(d, rows), "decisions": len(rows),
                            "finished": (d / "kpis.json").exists()})
        return {"runs": out}

    @r.get("/decisions")
    def decisions(run: str | None = Query(None, description="recorded run folder name; omitted = current run")):
        src = load_source(mgr, run)
        items = [public_decision(i, row) for i, row in enumerate(src["rows"])]
        note = None
        if src["strategy"] in NO_DECISION_STRATEGIES:
            note = NO_DECISION_STRATEGIES[src["strategy"]]
        elif src["status"] == "idle":
            note = "Aucune simulation lancée depuis le démarrage du backend."
        return {k: v for k, v in src.items() if k not in ("rows", "run_dir")} | {
            "count": len(items), "eligible": sum(1 for d in items if d["shap"]["eligible"]), "note": note,
            "decisions": items, "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls"}

    @r.get("/shap")
    def shap(index: int = Query(..., ge=0), run: str | None = Query(None)):
        src = load_source(mgr, run)
        if index >= len(src["rows"]):
            raise HTTPException(404, f"décision {index} introuvable ({len(src['rows'])} décisions dans ce run)")
        row = src["rows"][index]
        el = eligibility(row)
        if not el["eligible"]:
            raise HTTPException(422, {"code": "not_eligible", "message": el["reason"]})
        try:
            res = explain(row, src["run_dir"], from_file=src["source"] == "decisions.csv")
        except sx.ExplanationError as e:     # verification against the frozen table failed: no value is shown
            raise HTTPException(422, {"code": "verification_failed",
                                      "message": f"Vérification de la table Q-learning impossible : {e}"})
        res["index"] = index
        return res

    return r
