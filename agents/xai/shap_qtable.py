"""Exact Shapley explanation of the S3 Q-learning table (2026-10-28) - OFFLINE, READ-ONLY.

What is explained
    The output of the REAL frozen Q-table of strategy S3 (agents/decision/controllers.py, QLearningController)
    for one logged decision:  delta(x) = Q(x, ADVANCE) - Q(x, KEEP)   ("passer" minus "garder").
    delta > 0 means the table prefers to change the phase. This is exactly the comparison made by the controller
    when it follows its table (source "table apprise").

How (approach B validated by the team)
    * The state key is "tls|g|file_servie|file_autre|en_mouvement|duree_vert" (classes, see controllers.py).
    * The signal tls and the green phase g are KEPT FIXED: they define the context (the other 4 variables refer to
      the lanes of that phase). Only the 4 other variables receive a contribution.
    * Background = the states of the SAME signal and the SAME green phase present in the table, each weighted by its
      number of visits (sum of the two visit counters) = the training distribution of the table.
    * Interventional Shapley values computed EXACTLY: for every background state b, the 2^4 = 16 coalitions are all
      evaluated (no sampling, no approximation); the per-background values are then averaged with the visit weights.
    * Additivity:  base + sum(phi) = delta(x), with base = weighted mean of delta(b) over the retained background.

Missing and unreliable values (nothing is ever invented)
    * A "hybrid" state (some variables from x, the others from b) may not exist in the table. Then delta is undefined
      for that background state: the WHOLE background state is excluded (all its coalitions), and it is counted.
      Additivity stays exact on the retained background.
    * A table value is "unreliable" when one of its two actions was tried fewer than MIN_VISITS = 3 times, or when
      both values are equal (same rule as the controller). Unreliable values are USED as they are (they are the real
      table) but counted and reported.

What it does NOT do: it never imports SUMO/TraCI, never touches the controller, the orchestrator, the strategies,
the safety rules, the Q-table file or the simulation outputs. It only reads files and writes a NEW demo folder.

    python -m agents.xai.shap_qtable --out docs/shap_demo_v1          (run from the project root)
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / "sumo" / "lust_4_intersections" / "output"
DEFAULT_QTABLE = OUTPUT / "experiments_v1" / "rl" / "qtable_v4_FROZEN_ep26_eval.json"
DEFAULT_RUN = OUTPUT / "app_runs" / "20261022_141518_S3_rl_qlearning_x1_seed1_ambulance_prio"
DEFAULT_TLS = "-29958"            # Carrefour 4
DEFAULT_TIME_S = 26941.0          # 07:29:01

FEATURES = ("file_servie", "file_autre", "en_mouvement", "durée_vert")     # order of the state key after tls|g
FEATURE_LABELS = {"file_servie": "véhicules arrêtés sur les voies au vert",
                  "file_autre": "véhicules arrêtés sur une autre phase",
                  "en_mouvement": "véhicules en mouvement au vert",
                  "durée_vert": "durée du vert écoulée"}
# class labels = bins of controllers.py: Q_EDGES (0, 2, 5, 10), M_EDGES (0, 2, 5), T_EDGES (10, 20, 40)
CLASS_LABELS = {"file_servie": ["0", "1–2", "3–5", "6–10", "> 10"], "file_autre": ["0", "1–2", "3–5", "6–10", "> 10"],
                "en_mouvement": ["0", "1–2", "3–5", "> 5"], "durée_vert": ["≤ 10 s", "11–20 s", "21–40 s", "> 40 s"]}
MIN_VISITS = 3                    # = QLearningController.min_visits
KEEP, ADVANCE = 0, 1              # = agents.decision.controllers
LOG_ROUND_TOL = 5e-4 + 1e-9       # decisions.csv stores Q-values rounded to 3 decimals
ADDITIVITY_TOL = 1e-9


class ExplanationError(RuntimeError):
    """A check failed: no explanation is produced (never a misleading one)."""


class NotExplainable(ExplanationError):
    """The decision was not taken by the learned table (fallback rule S2, safety rule, other strategy...)."""


# ----------------------------------------------------------------------------------------------- Q-table (read-only)
@dataclass(frozen=True)
class QTable:
    q: dict          # key -> [Q_keep, Q_advance]
    n: dict          # key -> [visits_keep, visits_advance]
    meta: dict
    path: str = ""

    def has(self, key: str) -> bool:
        return key in self.q

    def delta(self, key: str) -> float:
        qk, qa = self.q[key]
        return float(qa) - float(qk)

    def visits(self, key: str) -> list:
        return list(self.n.get(key, [0, 0]))

    def reliable(self, key: str) -> bool:
        """Same trust rule as QLearningController.decide(): both actions tried >= MIN_VISITS times, different values."""
        if key not in self.q:
            return False
        v = self.n.get(key, [0, 0])
        return min(v) >= MIN_VISITS and self.q[key][0] != self.q[key][1]


def load_qtable(path: Path = DEFAULT_QTABLE) -> QTable:
    """Read-only: the file is only read (never opened for writing)."""
    path = Path(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    if "q" not in d or "n" not in d:
        raise ExplanationError(f"{path}: not a Q-table file (keys 'q' and 'n' expected)")
    return QTable(q=d["q"], n=d["n"], meta=d.get("meta", {}), path=str(path))


def make_key(tls: str, g: int, feats) -> str:
    return f"{tls}|{int(g)}|" + "|".join(str(int(v)) for v in feats)


def parse_key(key: str):
    parts = key.split("|")
    if len(parts) != 6:
        raise ExplanationError(f"unexpected state key {key!r}")
    return parts[0], int(parts[1]), tuple(int(v) for v in parts[2:])


# ------------------------------------------------------------------------------------------- logged decision checks
def read_decision(decisions_csv: Path, tls: str, time_s: float) -> dict:
    """Return the decisions.csv row of signal `tls` at `time_s` (exactly one row expected)."""
    with open(decisions_csv, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh, delimiter=";")
                if r.get("tls") == tls and abs(float(r.get("time_s", "nan")) - float(time_s)) < 1e-6]
    if len(rows) != 1:
        raise ExplanationError(f"{len(rows)} logged decision(s) for tls {tls} at t={time_s} in {decisions_csv} (exactly 1 expected)")
    row = dict(rows[0])
    row["explanation_json"] = json.loads(row["explanation"]) if row.get("explanation") else None
    return row


def check_learned_decision(row: dict) -> dict:
    """The decision must come from the learned table of S3 - never from the fallback rule S2 or a safety rule."""
    ex = row.get("explanation_json")
    if row.get("controller") != "S3_rl_qlearning":
        raise NotExplainable(f"controller {row.get('controller')!r}: only S3_rl_qlearning has a Q-table")
    if row.get("reason") != "agent_decision":
        raise NotExplainable(f"reason {row.get('reason')!r}: phase change forced by a rule, not decided by the table")
    if not ex:
        raise NotExplainable("no explanation recorded for this decision")
    src = ex.get("source", "")
    if src != "table apprise":
        raise NotExplainable(f"source {src!r}: this decision was not taken by the learned table")
    if ex.get("action") != "passer":
        raise ExplanationError(f"logged phase change but recorded action is {ex.get('action')!r}")
    return ex


def state_key_from_explanation(tls: str, ex: dict) -> str:
    s = ex["situation"]
    return make_key(tls, int(s["phase_verte"]), [int(s[f]) for f in FEATURES])


def verify_logged_values(table: QTable, key: str, ex: dict) -> dict:
    """The table must give back exactly what the controller logged at decision time."""
    if not table.has(key):
        raise ExplanationError(f"state {key} of the logged decision is not in the Q-table {table.path}")
    qk, qa = (float(v) for v in table.q[key])
    if abs(qk - float(ex["q_garder"])) > LOG_ROUND_TOL or abs(qa - float(ex["q_passer"])) > LOG_ROUND_TOL:
        raise ExplanationError(f"Q-values of the table ({qk:.6f}, {qa:.6f}) differ from the logged ones "
                               f"({ex['q_garder']}, {ex['q_passer']}): wrong table or wrong state")
    if table.visits(key) != list(ex["visites_garder_passer"]):
        raise ExplanationError(f"visit counts differ: table {table.visits(key)} vs logged {ex['visites_garder_passer']}")
    if not table.reliable(key):
        raise ExplanationError(f"state {key} is not trusted by the controller rule (visits {table.visits(key)})")
    d = qa - qk
    if d <= 0:
        raise ExplanationError(f"delta = {d:.6f} <= 0 although the table chose 'passer'")
    return {"q_garder": qk, "q_passer": qa, "delta": d, "visits_garder_passer": table.visits(key)}


# ------------------------------------------------------------------------------------------------- exact Shapley
def shapley_weights(m: int) -> dict:
    return {s: math.factorial(s) * math.factorial(m - s - 1) / math.factorial(m) for s in range(m)}


@dataclass
class ShapResult:
    tls: str
    phase: int
    x: tuple
    delta_x: float
    phi: list
    base: float
    background_total: int
    background_retained: int
    background_excluded: int
    excluded_examples: list = field(default_factory=list)
    weight_total: float = 0.0
    weight_retained: float = 0.0
    background_unreliable: int = 0
    evaluations: int = 0
    evaluations_unreliable: int = 0
    weighted_share_unreliable: float = 0.0
    additivity_error: float = 0.0
    retained_class_weights: list = field(default_factory=list)   # per variable: {class: visit weight} in the retained background

    @property
    def constant_variables(self) -> list:
        """Indices of variables with a single class in the retained background: their contribution is 0 BY CONSTRUCTION
        (x and background never differ on them unless x has another class), which says nothing about their importance."""
        return [i for i, c in enumerate(self.retained_class_weights) if len(c) <= 1]

    @property
    def sum_phi(self) -> float:
        return float(sum(self.phi))


def background_for(table: QTable, tls: str, g: int):
    """States of the same signal and the same green phase, weighted by their visits (sum of both counters)."""
    out = []
    for key in sorted(table.q):
        t, gg, feats = parse_key(key)
        if t == tls and gg == g:
            w = sum(table.visits(key))
            if w > 0:
                out.append((feats, float(w)))
    return out


def exact_shapley_delta(table: QTable, tls: str, g: int, x, background=None) -> ShapResult:
    """Exact interventional Shapley values of delta = Q(passer) - Q(garder) for state x (4 features), phase fixed."""
    x = tuple(int(v) for v in x)
    m = len(x)
    kx = make_key(tls, g, x)
    if not table.has(kx):
        raise ExplanationError(f"explained state {kx} is not in the Q-table (unseen state): nothing to explain")
    dx = table.delta(kx)
    bg = background if background is not None else background_for(table, tls, g)
    if not bg:
        raise ExplanationError(f"no background state for tls {tls}, phase {g}")
    w_sh = shapley_weights(m)
    coalitions = list(itertools.product((0, 1), repeat=m))       # 1 = feature taken from x
    phi_acc = [0.0] * m
    base_acc = w_ret = w_tot = w_unrel = 0.0
    n_ret = n_exc = n_bg_unrel = n_eval = n_eval_unrel = 0
    excluded = []
    cls_w = [dict() for _ in range(m)]
    for b, w in bg:
        b = tuple(int(v) for v in b)
        w_tot += w
        keys = {S: make_key(tls, g, [x[i] if S[i] else b[i] for i in range(m)]) for S in coalitions}
        missing = [k for k in keys.values() if not table.has(k)]
        if missing:                                               # undefined delta: exclude this background state
            n_exc += 1
            if len(excluded) < 10:
                excluded.append({"background": list(b), "missing_states": sorted(set(missing))[:4]})
            continue
        v = {S: table.delta(k) for S, k in keys.items()}
        for S, k in keys.items():
            n_eval += 1
            if not table.reliable(k):
                n_eval_unrel += 1
                w_unrel += w
        if not table.reliable(make_key(tls, g, b)):
            n_bg_unrel += 1
        for i in range(m):
            acc = 0.0
            for S in coalitions:
                if S[i]:
                    continue
                Si = tuple(1 if j == i else S[j] for j in range(m))
                acc += w_sh[sum(S)] * (v[Si] - v[S])
            phi_acc[i] += w * acc
        base_acc += w * v[(0,) * m]
        for i in range(m):
            cls_w[i][b[i]] = cls_w[i].get(b[i], 0.0) + w
        w_ret += w
        n_ret += 1
    if n_ret == 0:
        raise ExplanationError(f"all {n_exc} background states produce undefined hybrid states: no valid explanation")
    phi = [p / w_ret for p in phi_acc]
    base = base_acc / w_ret
    err = abs(base + sum(phi) - dx)
    res = ShapResult(tls=tls, phase=g, x=x, delta_x=dx, phi=phi, base=base, background_total=len(bg),
                     background_retained=n_ret, background_excluded=n_exc, excluded_examples=excluded,
                     weight_total=w_tot, weight_retained=w_ret, background_unreliable=n_bg_unrel,
                     evaluations=n_eval, evaluations_unreliable=n_eval_unrel,
                     weighted_share_unreliable=(w_unrel / (w_ret * len(coalitions))) if w_ret else 0.0,
                     additivity_error=err, retained_class_weights=cls_w)
    if err > ADDITIVITY_TOL:
        raise ExplanationError(f"additivity check failed: |base + sum(phi) - delta| = {err:.3e} > {ADDITIVITY_TOL}")
    return res


# ------------------------------------------------------------------------------------------ end-to-end explanation
def explain_logged_decision(run_dir: Path = DEFAULT_RUN, tls: str = DEFAULT_TLS, time_s: float = DEFAULT_TIME_S,
                            qtable_path: Path = DEFAULT_QTABLE) -> dict:
    row = read_decision(Path(run_dir) / "decisions.csv", tls, time_s)
    ex = check_learned_decision(row)
    table = load_qtable(qtable_path)
    key = state_key_from_explanation(tls, ex)
    logged = verify_logged_values(table, key, ex)
    _, g, x = parse_key(key)
    r = exact_shapley_delta(table, tls, g, x)
    if abs(r.delta_x - logged["delta"]) > 1e-12:
        raise ExplanationError("explained output differs from the verified delta")
    contributions = [{"variable": f, "label": FEATURE_LABELS[f], "class_index": x[i], "class": CLASS_LABELS[f][x[i]],
                      "shap": r.phi[i],
                      "background_classes_retained": {CLASS_LABELS[f][c]: w for c, w in sorted(r.retained_class_weights[i].items())},
                      "warning": ("constant in the retained background: contribution 0 by construction, NOT a proof that "
                                  "the variable has no effect") if i in r.constant_variables else None}
                     for i, f in enumerate(FEATURES)]
    return {
        "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
        "model": {"type": "tabular Q-learning (S3), frozen table", "file": _rel(qtable_path),
                  "episodes_trained": table.meta.get("episodes_trained"), "train_scales": sorted(set(table.meta.get("train_scales", [])))},
        "explained_output": "delta = Q(passer) - Q(garder)  (> 0: the table prefers to change the phase)",
        "method": "exact interventional Shapley values (2^4 coalitions per background state, no sampling); "
                  "signal and green phase fixed; background = states of the same signal and phase in the table, weighted by visits",
        "decision": {"run": _rel(run_dir), "tls": tls, "time_s": float(row["time_s"]), "clock": _clock(float(row["time_s"])),
                     "from_phase": int(row["from_phase"]), "to_phase": int(row["to_phase"]),
                     "green_duration_s": float(row["green_duration_s"]), "source": ex["source"], "action": ex["action"]},
        "state": {"key": key, "green_phase_index": g, **{f: {"class_index": x[i], "class": CLASS_LABELS[f][x[i]]} for i, f in enumerate(FEATURES)}},
        "logged_check": {"q_garder_logged": ex["q_garder"], "q_passer_logged": ex["q_passer"],
                         "q_garder_table": logged["q_garder"], "q_passer_table": logged["q_passer"],
                         "visits_garder_passer": logged["visits_garder_passer"], "ok": True},
        "delta": r.delta_x, "base_value": r.base, "contributions": contributions, "sum_contributions": r.sum_phi,
        "additivity": {"base_plus_sum": r.base + r.sum_phi, "delta": r.delta_x, "abs_error": r.additivity_error,
                       "tolerance": ADDITIVITY_TOL, "ok": r.additivity_error <= ADDITIVITY_TOL},
        "background": {"states_total": r.background_total, "states_retained": r.background_retained,
                       "states_excluded_missing_hybrid": r.background_excluded, "excluded_examples": r.excluded_examples,
                       "visit_weight_total": r.weight_total, "visit_weight_retained": r.weight_retained,
                       "states_retained_unreliable": r.background_unreliable,
                       "hybrid_evaluations": r.evaluations, "hybrid_evaluations_unreliable": r.evaluations_unreliable,
                       "weighted_share_unreliable_evaluations": r.weighted_share_unreliable},
        "limitations": [
            "SHAP describes how the variables moved the OUTPUT OF THE TABLE (delta), not a causal effect on traffic.",
            "Background = training distribution of the table (demand x5); the explained decision comes from a x1 run.",
            "Variables are classes (bins), not exact vehicle counts.",
            "A variable that is constant in the retained background gets 0 by construction (see 'warning').",
            "Some table values used in the calculation are unreliable (fewer than 3 visits): their share is reported.",
            "Only decisions taken by the learned table can be explained this way (not the fallback rule S2, not safety rules, not 'keep' decisions, which are not logged).",
        ],
    }


def _rel(p) -> str:
    """Path relative to the project root when possible (portable between Windows and Linux)."""
    try:
        return Path(p).resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(p)


def _clock(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def to_markdown(res: dict) -> str:
    d, b, a = res["decision"], res["background"], res["additivity"]
    lines = [f"# Explication SHAP exacte – décision réelle de S3 ({d['clock']}, feu {d['tls']}) – SIMULÉ", "",
             f"- Modèle expliqué : {res['model']['type']} (`{Path(res['model']['file']).name}`)",
             f"- Sortie expliquée : {res['explained_output']}",
             f"- Méthode : {res['method']}",
             f"- Décision : run `{Path(d['run']).name}`, source « {d['source']} », phase {d['from_phase']} → {d['to_phase']}",
             f"- Q(garder) = {res['logged_check']['q_garder_table']:.6f}, Q(passer) = {res['logged_check']['q_passer_table']:.6f} "
             f"(journal : {res['logged_check']['q_garder_logged']} / {res['logged_check']['q_passer_logged']}), "
             f"visites {res['logged_check']['visits_garder_passer']}", "",
             "| Variable | Classe observée | Contribution SHAP à Δ |", "|---|---|---|"]
    for c in res["contributions"]:
        lines.append(f"| {c['label']} | {c['class']} | {c['shap']:+.6f}{' (*)' if c['warning'] else ''} |")
    if any(c["warning"] for c in res["contributions"]):
        lines += ["", "(*) Variable constante dans le fond retenu : contribution nulle par construction, ce n'est PAS la preuve "
                  "que la variable est sans effet."]
    lines += ["", f"- Valeur de référence (Δ moyen du fond retenu) : {res['base_value']:+.6f}",
              f"- Somme des contributions : {res['sum_contributions']:+.6f}",
              f"- Référence + somme = {a['base_plus_sum']:+.6f} ; Δ = {a['delta']:+.6f} ; écart = {a['abs_error']:.2e} (tolérance {a['tolerance']:.0e})",
              f"- Fond : {b['states_total']} états, {b['states_retained']} retenus, {b['states_excluded_missing_hybrid']} exclus (état mélangé absent de la table) ; "
              f"{b['states_retained_unreliable']} états retenus peu fiables ; {b['hybrid_evaluations_unreliable']}/{b['hybrid_evaluations']} évaluations peu fiables "
              f"({100 * b['weighted_share_unreliable_evaluations']:.1f} % en poids)", "", "## Limites", ""]
    lines += [f"- {x}" for x in res["limitations"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, default=DEFAULT_RUN)
    p.add_argument("--tls", default=DEFAULT_TLS)
    p.add_argument("--time", type=float, default=DEFAULT_TIME_S)
    p.add_argument("--qtable", type=Path, default=DEFAULT_QTABLE)
    p.add_argument("--out", type=Path, required=True, help="NEW folder (refused if it already exists)")
    a = p.parse_args(argv)
    if a.out.exists():
        print(f"refused: {a.out} already exists (nothing is overwritten)", file=sys.stderr)
        return 2
    try:
        res = explain_logged_decision(a.run, a.tls, a.time, a.qtable)
    except ExplanationError as e:
        print(f"NO EXPLANATION PRODUCED - check failed: {e}", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True)
    (a.out / "shap_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "shap_result.md").write_text(to_markdown(res), encoding="utf-8")
    print(to_markdown(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
