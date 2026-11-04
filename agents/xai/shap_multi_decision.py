"""Multi-decision stability study of the exact SHAP explanations of the S3 Q-table (approved protocol, 29/10/2026).

Question: for the REAL decisions already logged by S3, does the explanation change when only the background
(reference) changes?  Three backgrounds are compared for every distinct explained state:
    A  current: retained background states (same signal, same green phase, hybrid states present), weight = visits
    B  the SAME retained states as A, weight 1 each
    C  the retained states of A that are RELIABLE (each action tried >= 3 times, different Q-values), weight = visits
       (only if at least MIN_RELIABLE_BG = 5 states remain; otherwise "C not computable")

Read-only. Nothing is simulated or trained; the frozen Q-table and the decision logs are only read, and
agents/xai/shap_qtable.py and agents/xai/shap_stability.py are reused unchanged.

Protocol (fixed BEFORE any result was computed)
  Inclusion (per logged decision): S3 run that logs the observed state (column "explanation"); controller S3,
      reason agent_decision, source "table apprise", action "passer" (shap_qtable.check_learned_decision);
      logged Q-values and visits equal to the frozen table, trusted state, delta > 0 (shap_qtable.verify_logged_values).
  Exclusion: every other row is written to exclusions.csv with its reason (nothing is dropped silently).
  Unit of analysis: the DISTINCT state (signal, phase, state). The explanation of a state is deterministic, so
      repeated decisions of the same state are NOT independent observations. Main result: unweighted (one state =
      one unit); secondary result: weighted by the number of decisions. Results per signal. No statistical test.
  Measures, per state and per pair of backgrounds (A-B, A-C, B-C):
      informative variable: not constant in either background AND |phi| >= 5 % of sum|phi| in at least one of the two
      sign inversion: informative, non-negligible in BOTH (>= 5 % of their own sum|phi|) and opposite signs
      main variable: set of variables with the largest |phi| (ties compared as sets)
      shape distance: sum|phi1 - phi2| / (sum|phi1| + sum|phi2|) in [0, 1]
      base value difference, weighted share of unreliable hybrid evaluations
      Kendall tau-b of |phi| over the informative variables, only if there are at least 3 of them
  Classification of a state:
      non evaluable : fewer than 2 informative variables, or C not computable
      stable        : same main variable in A, B and C and no sign inversion in any pair
      partial       : same main variable in A, B and C but at least one sign inversion
      unstable      : the main variable differs in at least one background
      flagged apart : C identical to A (every retained state is reliable): A-C agreement proves nothing there
  Global reading (unweighted, evaluable states): >= 80 % stable or partial -> "plutôt robuste";
      < 50 % -> "sensible"; otherwise "mitigé". Per-signal results are descriptive only.

    python -m agents.xai.shap_multi_decision --out docs/shap_multi_decision_v1
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from agents.xai import shap_qtable as sx
from agents.xai import shap_stability as ss

RUNS_DIR = sx.OUTPUT / "app_runs"
S3_RUN_GLOB = "*_S3_rl_qlearning_*"
MIN_RELIABLE_BG = 5            # C is computed only with at least this many reliable retained states
NEGLIGIBLE_SHARE = 0.05        # |phi| < 5 % of sum|phi| of that background is negligible
ROBUST_SHARE, SENSITIVE_SHARE = 0.80, 0.50
MATCH_TOL = 1e-12
METHODS = ("A", "B", "C")
PAIRS = (("A", "B"), ("A", "C"), ("B", "C"))
F = sx.FEATURES


class StudyError(Exception):
    """A protocol check failed: the study stops and writes nothing."""


class NoRetainedBackground(Exception):
    """Inclusion criterion 4 not met for a state: no retained background state (A and B undefined)."""


# --------------------------------------------------------------------------------------------- 1. cases
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _exclusion_code(row: dict, ex) -> str:
    """Short code of why a row is not a learned decision (the check itself is done by shap_qtable)."""
    if row.get("controller") != "S3_rl_qlearning":
        return "other_controller"
    if row.get("reason") != "agent_decision":
        return f"rule:{row.get('reason')}"
    if not ex:
        return "no_explanation"
    if ex.get("source") != "table apprise":
        return "fallback_S2" if "secours" in str(ex.get("source", "")) else "other_source"
    return "inconsistent_log"


def collect_cases(run_dirs, table: sx.QTable):
    """Apply the inclusion criteria to every row of every run. Returns (cases, exclusions, runs)."""
    cases, exclusions, runs = [], [], []
    for run in run_dirs:
        run = Path(run)
        f = run / "decisions.csv"
        info = {"run": sx._rel(run), "decisions_csv": f.exists()}
        if not f.exists():
            info.update(rows=0, logs_state=False, included=0)
            runs.append(info)
            continue
        with open(f, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            rows = list(reader)
            cols = reader.fieldnames or []
        logs_state = "explanation" in cols
        n_inc = 0
        for line, r in enumerate(rows, start=2):
            base = {"run": sx._rel(run), "line": line, "time_s": r.get("time_s"), "tls": r.get("tls"),
                    "reason": r.get("reason"), "controller": r.get("controller")}
            if not logs_state:
                exclusions.append({**base, "code": "run_without_logged_state",
                                   "detail": "decisions.csv has no 'explanation' column"})
                continue
            r = dict(r)
            try:
                r["explanation_json"] = json.loads(r["explanation"]) if r.get("explanation") else None
            except json.JSONDecodeError:
                exclusions.append({**base, "code": "explanation_unreadable", "detail": "invalid JSON"})
                continue
            ex_raw = r["explanation_json"]
            try:
                ex = sx.check_learned_decision(r)
            except sx.ExplanationError as e:          # NotExplainable is a subclass
                exclusions.append({**base, "code": _exclusion_code(r, ex_raw),
                                   "detail": (ex_raw or {}).get("source", str(e)) if ex_raw else str(e)})
                continue
            try:
                key = sx.state_key_from_explanation(r["tls"], ex)
                checked = sx.verify_logged_values(table, key, ex)
            except (sx.ExplanationError, KeyError, ValueError) as e:
                exclusions.append({**base, "code": "log_vs_table_mismatch", "detail": str(e)})
                continue
            tls, g, x = sx.parse_key(key)
            cases.append({"run": sx._rel(run), "line": line, "time_s": float(r["time_s"]), "tls": tls, "phase": g,
                          "state": list(x), "state_key": key, "q_garder": checked["q_garder"],
                          "q_passer": checked["q_passer"], "delta": checked["delta"],
                          "visits_garder_passer": checked["visits_garder_passer"]})
            n_inc += 1
        info.update(rows=len(rows), logs_state=logs_state, included=n_inc)
        runs.append(info)
    return cases, exclusions, runs


def group_by_state(cases) -> dict:
    """Distinct explained states: repeated decisions of one state form ONE unit of analysis."""
    states = {}
    for c in cases:
        s = states.setdefault(c["state_key"], {"state_key": c["state_key"], "tls": c["tls"], "phase": c["phase"],
                                               "state": c["state"], "n_decisions": 0, "times": [],
                                               "delta": c["delta"]})
        if abs(s["delta"] - c["delta"]) > MATCH_TOL:
            raise StudyError(f"state {c['state_key']} has two different delta values")
        s["n_decisions"] += 1
        s["times"].append(c["time_s"])
    return states


# ---------------------------------------------------------------------------------------- 2. backgrounds
def build_backgrounds(table: sx.QTable, tls: str, g: int, x) -> dict:
    """A, B and C exactly as in the protocol, with construction checks."""
    full = sx.background_for(table, tls, g)
    a = ss.retained_background(table, tls, g, x, full)
    b = [(s, 1.0) for s, _ in a]
    c = [(s, w) for s, w in a if table.reliable(sx.make_key(tls, g, s))]
    # C must be exactly "A restricted to reliable states": recompute it from the reliable part of the full background
    c_check = ss.retained_background(table, tls, g, x,
                                     [(s, w) for s, w in full if table.reliable(sx.make_key(tls, g, s))])
    if [s for s, _ in c] != [s for s, _ in c_check] or [w for _, w in c] != [w for _, w in c_check]:
        raise StudyError(f"{tls}|{g}: background C is not A restricted to reliable states")
    return {"full": full, "A": a, "B": b, "C": c,
            "C_computable": len(c) >= MIN_RELIABLE_BG, "C_equals_A": c == a}


def explain_three(table: sx.QTable, tls: str, g: int, x) -> dict:
    """Exact SHAP with the three backgrounds + reproducibility and additivity checks."""
    bgs = build_backgrounds(table, tls, g, x)
    if not bgs["A"]:
        raise NoRetainedBackground(f"{tls}|{g}|{x}: no retained background state")
    default = sx.exact_shapley_delta(table, tls, g, x)                 # the published method (A)
    res = {"A": sx.exact_shapley_delta(table, tls, g, x, background=bgs["A"]),
           "B": sx.exact_shapley_delta(table, tls, g, x, background=bgs["B"])}
    if default.background_retained != len(bgs["A"]):
        raise StudyError(f"{tls}|{g}|{x}: retained set differs from shap_qtable")
    if abs(res["A"].base - default.base) > MATCH_TOL or any(abs(p - q) > MATCH_TOL for p, q in zip(res["A"].phi, default.phi)):
        raise StudyError(f"{tls}|{g}|{x}: background A does not reproduce the default explanation")
    if res["B"].background_retained != len(bgs["A"]) or res["B"].background_excluded != 0:
        raise StudyError(f"{tls}|{g}|{x}: background B does not use exactly the states of A")
    if bgs["C_computable"]:
        res["C"] = sx.exact_shapley_delta(table, tls, g, x, background=bgs["C"])
        if res["C"].background_retained != len(bgs["C"]) or res["C"].background_excluded != 0:
            raise StudyError(f"{tls}|{g}|{x}: background C lost states")
    for m, r in res.items():
        if r.additivity_error > sx.ADDITIVITY_TOL:
            raise StudyError(f"{tls}|{g}|{x}: additivity fails for {m}")
        if r.delta_x != default.delta_x:
            raise StudyError(f"{tls}|{g}|{x}: delta differs for {m}")
    return {"backgrounds": bgs, "results": res}


# ------------------------------------------------------------------------------------------- 3. measures
def _abs_sum(phi) -> float:
    return float(sum(abs(p) for p in phi))


def non_negligible(phi) -> list:
    s = _abs_sum(phi)
    return [s > 0 and abs(p) >= NEGLIGIBLE_SHARE * s for p in phi]


def main_variables(phi) -> list:
    """Indices with the largest |phi| (ties within 1e-12); empty if every phi is 0."""
    m = max(abs(p) for p in phi)
    if m <= ss.SIGN_TOL:
        return []
    return [i for i, p in enumerate(phi) if abs(abs(p) - m) <= MATCH_TOL]


def main_margin(phi):
    """DESCRIPTIVE only (not used for classification): (|phi| 1st - |phi| 2nd) / sum|phi|."""
    s = _abs_sum(phi)
    if s <= 0:
        return None
    a = sorted((abs(p) for p in phi), reverse=True)
    return (a[0] - a[1]) / s


def kendall_tau_b(a, b):
    """Kendall tau-b (ties handled); None if undefined."""
    n = len(a)
    conc = disc = ta = tb = 0
    for i in range(n):
        for j in range(i + 1, n):
            da, db = a[i] - a[j], b[i] - b[j]
            if da == 0 and db == 0:
                continue
            if da == 0:
                ta += 1
            elif db == 0:
                tb += 1
            elif (da > 0) == (db > 0):
                conc += 1
            else:
                disc += 1
    den = ((conc + disc + ta) * (conc + disc + tb)) ** 0.5
    return None if den == 0 else (conc - disc) / den


def pair_measures(phi1, phi2, const1, const2) -> dict:
    nn1, nn2 = non_negligible(phi1), non_negligible(phi2)
    const = set(const1) | set(const2)
    informative = [i for i in range(len(phi1)) if i not in const and (nn1[i] or nn2[i])]
    inversions = [i for i in informative if nn1[i] and nn2[i]
                  and {ss.sign(phi1[i]), ss.sign(phi2[i])} == {"+", "-"}]
    den = _abs_sum(phi1) + _abs_sum(phi2)
    tau = (kendall_tau_b([abs(phi1[i]) for i in informative], [abs(phi2[i]) for i in informative])
           if len(informative) >= 3 else None)
    return {"informative": [F[i] for i in informative],
            "sign_inversions": [F[i] for i in inversions],
            "same_main_variable": main_variables(phi1) == main_variables(phi2),
            "shape_distance": (sum(abs(p - q) for p, q in zip(phi1, phi2)) / den) if den > 0 else 0.0,
            "kendall_tau_b": tau}


def classify(phis: dict, consts: dict, c_computable: bool, c_equals_a: bool) -> dict:
    """Protocol classification of one state. phis/consts: {method: list} (C may be missing)."""
    out = {"pairs": {}, "C_equals_A": c_equals_a}
    present = [m for m in METHODS if m in phis]
    for m1, m2 in PAIRS:
        if m1 in phis and m2 in phis:
            out["pairs"][f"{m1}-{m2}"] = pair_measures(phis[m1], phis[m2], consts[m1], consts[m2])
    const_all = set().union(*(set(consts[m]) for m in present))
    informative = sorted({i for i in range(len(F)) if i not in const_all
                          and any(non_negligible(phis[m])[i] for m in present)})
    out["informative_variables"] = [F[i] for i in informative]
    out["main_variable"] = {m: [F[i] for i in main_variables(phis[m])] for m in present}
    if not c_computable:
        out.update(category="non_evaluable", reason=f"C not computable (< {MIN_RELIABLE_BG} reliable retained states)")
        return out
    if len(informative) < 2:
        out.update(category="non_evaluable", reason=f"{len(informative)} informative variable(s) (< 2)")
        return out
    same_main = len({tuple(out["main_variable"][m]) for m in METHODS}) == 1 and out["main_variable"]["A"] != []
    inversions = any(p["sign_inversions"] for p in out["pairs"].values())
    out["category"] = "unstable" if not same_main else ("partial" if inversions else "stable")
    out["reason"] = ""
    mains = set().union(*(set(v) for v in out["main_variable"].values()))
    out["inversion_on_main_variable"] = sorted({v for p in out["pairs"].values() for v in p["sign_inversions"] if v in mains})
    agree = {k: (not p["sign_inversions"]) and p["same_main_variable"] for k, p in out["pairs"].items()}
    out["pair_agreement"] = agree
    out["pattern"] = ("all agree" if all(agree.values()) else
                      "A≈C, B differs" if agree["A-C"] and not agree["A-B"] and not agree["B-C"] else
                      "A≈B, C differs" if agree["A-B"] and not agree["A-C"] and not agree["B-C"] else
                      "B≈C, A differs" if agree["B-C"] and not agree["A-B"] and not agree["A-C"] else
                      "all differ" if not any(agree.values()) else "mixed")
    return out


def verdict(share_ok):
    if share_ok is None:
        return "aucun état évaluable"
    if share_ok >= ROBUST_SHARE:
        return "plutôt robuste"
    if share_ok < SENSITIVE_SHARE:
        return "sensible"
    return "mitigé"


def aggregate(per_state: list) -> dict:
    cats = ("stable", "partial", "unstable", "non_evaluable")

    def block(items):
        n = Counter(s["category"] for s in items)
        w = Counter()
        for s in items:
            w[s["category"]] += s["n_decisions"]
        ev, ev_w = sum(n[c] for c in cats[:3]), sum(w[c] for c in cats[:3])
        ok, ok_w = n["stable"] + n["partial"], w["stable"] + w["partial"]
        dist = {}
        for pair in ("A-B", "A-C", "B-C"):
            vals = sorted(s["pairs"][pair]["shape_distance"] for s in items if pair in s["pairs"])
            taus = [s["pairs"][pair]["kendall_tau_b"] for s in items
                    if pair in s["pairs"] and s["pairs"][pair]["kendall_tau_b"] is not None]
            dist[pair] = {"states": len(vals),
                          "shape_distance_min": vals[0] if vals else None,
                          "shape_distance_median": (vals[len(vals) // 2] if len(vals) % 2 else
                                                    (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2) if vals else None,
                          "shape_distance_max": vals[-1] if vals else None,
                          "states_with_sign_inversion": sum(1 for s in items if pair in s["pairs"] and s["pairs"][pair]["sign_inversions"]),
                          "kendall_tau_b_defined": len(taus),
                          "kendall_tau_b_median": (sorted(taus)[len(taus) // 2] if len(taus) % 2 else
                                                   sum(sorted(taus)[len(taus) // 2 - 1:len(taus) // 2 + 1]) / 2) if taus else None}
        return {"states": len(items), "decisions": sum(s["n_decisions"] for s in items),
                "unweighted": {c: n[c] for c in cats}, "weighted_by_decisions": {c: w[c] for c in cats},
                "evaluable_states": ev, "share_stable_or_partial": ok / ev if ev else None,
                "share_stable_or_partial_weighted": ok_w / ev_w if ev_w else None,
                "C_equals_A_states": sum(1 for s in items if s["C_equals_A"]),
                "C_equals_A_and_stable": sum(1 for s in items if s["C_equals_A"] and s["category"] == "stable"),
                "partial_with_inversion_on_main_variable": sum(1 for s in items if s["category"] == "partial"
                                                               and s.get("inversion_on_main_variable_descriptive")),
                "patterns": dict(Counter(s.get("pattern") for s in items if s.get("pattern"))),
                "pairs": dist}
    total = block(per_state)
    total["reading"] = verdict(total["share_stable_or_partial"])
    by_tls = {t: block([s for s in per_state if s["tls"] == t]) for t in sorted({s["tls"] for s in per_state})}
    return {"total": total, "by_signal": by_tls}


# ----------------------------------------------------------------------------------------------- 4. run
def study(run_dirs=None, qtable_path: Path = sx.DEFAULT_QTABLE) -> dict:
    run_dirs = sorted(Path(RUNS_DIR).glob(S3_RUN_GLOB)) if run_dirs is None else [Path(r) for r in run_dirs]
    inputs = [Path(qtable_path)] + [Path(r) / "decisions.csv" for r in run_dirs if (Path(r) / "decisions.csv").exists()]
    before = {sx._rel(p): (_sha(p), p.stat().st_mtime_ns) for p in inputs}
    table = sx.load_qtable(Path(qtable_path))
    cases, exclusions, runs = collect_cases(run_dirs, table)
    states = group_by_state(cases)
    per_state = []
    for key in sorted(states, key=lambda k: (states[k]["tls"], states[k]["phase"], states[k]["state"])):
        s = states[key]
        try:
            e = explain_three(table, s["tls"], s["phase"], tuple(s["state"]))
        except NoRetainedBackground:
            per_state.append({"state_key": key, "tls": s["tls"], "phase": s["phase"], "state": s["state"],
                              "n_decisions": s["n_decisions"], "first_time_s": min(s["times"]),
                              "last_time_s": max(s["times"]), "delta": s["delta"],
                              "background_total": len(sx.background_for(table, s["tls"], s["phase"])),
                              "retained_A": 0, "retained_C": 0, "C_computable": False, "C_equals_A": False,
                              "methods": {}, "category": "non_evaluable",
                              "reason": "no retained background state (A and B undefined)",
                              "informative_variables": [], "main_variable": {}, "pairs": {}, "pattern": None})
            continue
        res, bgs = e["results"], e["backgrounds"]
        phis = {m: list(r.phi) for m, r in res.items()}
        consts = {m: list(r.constant_variables) for m, r in res.items()}
        cl = classify(phis, consts, bgs["C_computable"], bgs["C_equals_A"])
        per_state.append({
            "state_key": key, "tls": s["tls"], "phase": s["phase"], "state": s["state"],
            "n_decisions": s["n_decisions"], "first_time_s": min(s["times"]), "last_time_s": max(s["times"]),
            "delta": s["delta"], "background_total": len(bgs["full"]), "retained_A": len(bgs["A"]),
            "retained_C": len(bgs["C"]), "C_computable": bgs["C_computable"], "C_equals_A": bgs["C_equals_A"],
            "methods": {m: {"phi": dict(zip(F, r.phi)), "base_value": r.base, "sum_phi": r.sum_phi,
                            "additivity_error": r.additivity_error, "constant_variables": [F[i] for i in r.constant_variables],
                            "main_margin_descriptive": main_margin(r.phi),
                            "background_retained": r.background_retained, "weight_retained": r.weight_retained,
                            "weighted_share_unreliable_evaluations": r.weighted_share_unreliable}
                        for m, r in res.items()},
            **{k: cl[k] for k in ("category", "reason", "informative_variables", "main_variable", "pairs")},
            "inversion_on_main_variable_descriptive": cl.get("inversion_on_main_variable", []),
            "pattern": cl.get("pattern"),
        })
    after = {sx._rel(p): (_sha(p), p.stat().st_mtime_ns) for p in inputs}
    if before != after:
        raise StudyError("an input file changed during the study")
    rows_total = sum(r.get("rows", 0) for r in runs)
    if len(cases) + len(exclusions) != rows_total:
        raise StudyError("some rows are neither included nor excluded")
    return {
        "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
        "question": "Do exact SHAP explanations of real logged S3 decisions change when only the background changes (A visits / B uniform / C reliable only)?",
        "protocol": {"min_reliable_background_C": MIN_RELIABLE_BG, "negligible_share": NEGLIGIBLE_SHARE,
                     "robust_share": ROBUST_SHARE, "sensitive_share": SENSITIVE_SHARE,
                     "additivity_tolerance": sx.ADDITIVITY_TOL, "unit_of_analysis": "distinct state (signal, phase, state)"},
        "qtable": sx._rel(Path(qtable_path)),
        "inputs_sha256": {k: v[0] for k, v in before.items()},
        "inputs_unchanged": True,
        "runs": runs,
        "rows_total": rows_total, "decisions_included": len(cases), "rows_excluded": len(exclusions),
        "exclusions_by_code": dict(Counter(e["code"] for e in exclusions)),
        "exclusions_by_detail": [{"code": c, "detail": d, "rows": n} for (c, d), n in
                                 Counter((e["code"], e["detail"]) for e in exclusions).most_common()],
        "summary": aggregate(per_state),
        "per_state": per_state,
        "_cases": cases, "_exclusions": exclusions,
    }


# -------------------------------------------------------------------------------------------- 5. output
def _f(v):
    return "" if v is None else (repr(v) if isinstance(v, float) else str(v))


def write_outputs(out: Path, r: dict):
    out.mkdir(parents=True)
    with open(out / "cases.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["run", "line", "time_s", "tls", "phase", "state_key", "q_garder", "q_passer", "delta", "visits_garder_passer"])
        for c in r["_cases"]:
            w.writerow([c["run"], c["line"], _f(c["time_s"]), c["tls"], c["phase"], c["state_key"], _f(c["q_garder"]),
                        _f(c["q_passer"]), _f(c["delta"]), "/".join(map(str, c["visits_garder_passer"]))])
    with open(out / "exclusions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["run", "line", "time_s", "tls", "reason", "controller", "code", "detail"])
        for e in r["_exclusions"]:
            w.writerow([e["run"], e["line"], e["time_s"], e["tls"], e["reason"], e["controller"], e["code"], e["detail"]])
    with open(out / "per_state.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        head = ["state_key", "tls", "phase", "n_decisions", "delta", "background_total", "retained_A", "retained_C",
                "C_computable", "C_equals_A", "category", "reason", "pattern", "informative_variables",
                "inversion_on_main_variable_descriptive"]
        for m in METHODS:
            head += [f"phi_{m}_{v}" for v in F] + [f"base_{m}", f"main_{m}", f"main_margin_{m}", f"constant_{m}", f"unreliable_share_{m}"]
        for p in ("A-B", "A-C", "B-C"):
            head += [f"sign_inversions_{p}", f"same_main_{p}", f"shape_distance_{p}", f"kendall_tau_b_{p}"]
        w.writerow(head)
        for s in r["per_state"]:
            row = [s["state_key"], s["tls"], s["phase"], s["n_decisions"], _f(s["delta"]), s["background_total"],
                   s["retained_A"], s["retained_C"], s["C_computable"], s["C_equals_A"], s["category"], s["reason"],
                   s["pattern"] or "", "|".join(s["informative_variables"]),
                   "|".join(s.get("inversion_on_main_variable_descriptive", []))]
            for m in METHODS:
                mm = s["methods"].get(m)
                if mm is None:
                    row += ["not computable"] * (len(F) + 5)
                else:
                    row += [_f(mm["phi"][v]) for v in F] + [_f(mm["base_value"]), "|".join(s["main_variable"].get(m, [])),
                                                             _f(mm["main_margin_descriptive"]),
                                                             "|".join(mm["constant_variables"]),
                                                             _f(mm["weighted_share_unreliable_evaluations"])]
            for p in ("A-B", "A-C", "B-C"):
                pm = s["pairs"].get(p)
                row += (["not computable"] * 4 if pm is None else
                        ["|".join(pm["sign_inversions"]), pm["same_main_variable"], _f(pm["shape_distance"]),
                         _f(pm["kendall_tau_b"]) if pm["kendall_tau_b"] is not None else "not applicable (< 3 informative)"])
            w.writerow(row)
    public = {k: v for k, v in r.items() if not k.startswith("_")}
    (out / "per_state.json").write_text(json.dumps(public["per_state"], ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {k: v for k, v in public.items() if k != "per_state"}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "REPORT.md").write_text(to_markdown(r), encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")


CAT_FR = {"stable": "stable", "partial": "partiellement stable", "unstable": "instable", "non_evaluable": "non évaluable"}


def _esc(v) -> str:
    """Markdown table cell: '|' inside a state key would split the cell."""
    return str(v).replace("|", "\\|")


def _pct(v):
    return "—" if v is None else f"{100 * v:.1f} %"


def to_markdown(r: dict) -> str:
    T = r["summary"]["total"]
    L = ["# Étude SHAP multi-décision — stabilité selon le fond de référence", "",
         f"Données : **simulation SUMO** ({r['data_origin']}). Table Q gelée : `{r['qtable']}`. "
         "Rien n'a été simulé ni réentraîné ; les fichiers d'entrée sont inchangés (empreintes avant/après identiques).", "",
         "Fonds : **A** visites (méthode actuelle) · **B** uniforme sur les mêmes états · "
         f"**C** états fiables de A, pondérés par les visites (calculé si ≥ {MIN_RELIABLE_BG} états).", "",
         "## 1. Données", "",
         "| Run | Lignes | État enregistré | Décisions retenues |", "|---|---|---|---|"]
    for ru in r["runs"]:
        L.append(f"| `{ru['run'].split('/')[-1]}` | {ru.get('rows', 0)} | {'oui' if ru.get('logs_state') else 'non'} | {ru.get('included', 0)} |")
    L += ["", f"{r['decisions_included']} décisions retenues sur {r['rows_total']} lignes ; {r['rows_excluded']} exclues :", "",
          "| Code | Détail | Lignes |", "|---|---|---|"]
    for e in r["exclusions_by_detail"]:
        L.append(f"| {_esc(e['code'])} | {_esc(e['detail'])} | {e['rows']} |")
    L += ["", f"Unité d'analyse : **l'état distinct** ({T['states']} états pour {T['decisions']} décisions).", "",
          "## 2. Résultat principal (non pondéré : un état = une unité)", "",
          "| Catégorie | États | Décisions (pondéré) |", "|---|---|---|"]
    for c in ("stable", "partial", "unstable", "non_evaluable"):
        L.append(f"| {CAT_FR[c]} | {T['unweighted'][c]} | {T['weighted_by_decisions'][c]} |")
    L += ["", f"- États évaluables : {T['evaluable_states']} ; part stable ou partiellement stable : "
              f"**{_pct(T['share_stable_or_partial'])}** (pondérée par les décisions : {_pct(T['share_stable_or_partial_weighted'])}).",
          f"- Lecture fixée à l'avance (≥ {int(ROBUST_SHARE * 100)} % plutôt robuste, < {int(SENSITIVE_SHARE * 100)} % sensible) : **{T['reading']}**.",
          f"- États où C = A (tous les états retenus sont fiables, accord A–C non probant) : {T['C_equals_A_states']} "
          f"(dont {T['C_equals_A_and_stable']} classés stables).",
          f"- Parmi les états partiellement stables, {T['partial_with_inversion_on_main_variable']} ont une inversion de signe "
          "**sur la variable principale elle-même** (même variable en tête, sens opposé) : le protocole les classe "
          "« partiellement stables », mais ce désaccord est sérieux (indicateur descriptif, non utilisé pour le classement).",
          f"- Profils d'accord : " + ", ".join(f"{k} : {v}" for k, v in sorted(T["patterns"].items())) + ".", "",
          "| Paire | États | Avec inversion de signe | Distance de forme min / médiane / max | τ de Kendall défini | τ médian |",
          "|---|---|---|---|---|---|"]
    for p, d in T["pairs"].items():
        dd = "—" if d["shape_distance_median"] is None else f"{d['shape_distance_min']:.3f} / {d['shape_distance_median']:.3f} / {d['shape_distance_max']:.3f}"
        tau = "—" if d["kendall_tau_b_median"] is None else f"{d['kendall_tau_b_median']:.3f}"
        L.append(f"| {p} | {d['states']} | {d['states_with_sign_inversion']} | {dd} | {d['kendall_tau_b_defined']} | {tau} |")
    L += ["", "## 3. Par intersection (descriptif uniquement)", "",
          "| Feu | États | Décisions | Stable | Partiel | Instable | Non évaluable | Part stable/partiel | C = A |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t, b in r["summary"]["by_signal"].items():
        u = b["unweighted"]
        L.append(f"| {t} | {b['states']} | {b['decisions']} | {u['stable']} | {u['partial']} | {u['unstable']} | "
                 f"{u['non_evaluable']} | {_pct(b['share_stable_or_partial'])} | {b['C_equals_A_states']} |")
    L += ["", "## 4. Détail par état", "",
          "| État | Déc. | Retenus A / C | Catégorie | Variable principale A / B / C | Inversions de signe | Remarque |",
          "|---|---|---|---|---|---|---|"]
    for s in r["per_state"]:
        mv = " / ".join(",".join(s["main_variable"].get(m, ["—"])) or "—" if m in s["main_variable"] else "—" for m in METHODS)
        inv = "; ".join(f"{p}: {','.join(v['sign_inversions'])}" for p, v in s["pairs"].items() if v["sign_inversions"]) or "aucune"
        note = []
        if s["reason"]:
            note.append(s["reason"])
        if s["C_equals_A"]:
            note.append("C = A")
        if s.get("inversion_on_main_variable_descriptive"):
            note.append("inversion sur la variable principale : " + ", ".join(s["inversion_on_main_variable_descriptive"]))
        const = sorted(set().union(*(set(m["constant_variables"]) for m in s["methods"].values())))
        if const:
            note.append("constante(s) : " + ", ".join(const))
        L.append(f"| `{_esc(s['state_key'])}` | {s['n_decisions']} | {s['retained_A']} / {s['retained_C']} | {CAT_FR[s['category']]} | "
                 f"{mv} | {inv} | {'; '.join(note)} |")
    L += ["", "## 5. Contrôles", "",
          "- Additivité vérifiée pour chaque état et chaque fond (tolérance 1e-9).",
          "- Fond A identique à l'explication par défaut de `shap_qtable` (écart ≤ 1e-12) pour chaque état.",
          "- Fond B : exactement les états de A, poids 1. Fond C : exactement A restreint aux états fiables "
          "(recalculé indépendamment à partir du fond complet).",
          "- Chaque ligne des journaux est soit retenue, soit exclue avec un motif.",
          "- Empreintes SHA-256 et dates des fichiers d'entrée identiques avant et après.", "",
          "Mesure descriptive ajoutée (non utilisée pour le classement) : `main_margin_*` dans `per_state.csv` = écart entre "
          "la 1re et la 2e |contribution|, rapporté à Σ|φ|. Une petite marge signale qu'un changement de variable principale "
          "peut venir d'une quasi-égalité.", "",
          "## 6. Limites", "",
          "- Un seul run exploitable (×1, graine 1, 07:00–08:00, priorité ambulance) ; la table a été entraînée à ×5.",
          "- Seules les décisions « passer » de la table sont explicables (S2, règles et « garder » exclus) : l'échantillon favorise les états bien appris.",
          "- Les états d'un même feu et d'une même phase partagent presque le même fond : ils ne sont pas indépendants. Aucun test statistique.",
          "- Une contribution nulle d'une variable constante ne prouve rien sur son effet. Même dans C, des états hybrides peuvent être peu fiables.",
          "- SHAP décrit la sortie de la table Q, pas un effet causal sur le trafic. Les seuils (5 %, 80 %, 50 %) sont des conventions fixées avant le calcul.", ""]
    return "\n".join(L)


README = """# Étude SHAP multi-décision — comment reproduire (Windows)

Module : `agents/xai/shap_multi_decision.py` · tests : `tests/test_xai_shap_multi_decision.py`.
Lecture seule : table Q gelée et `decisions.csv` des runs S3 existants. Aucune simulation, aucun entraînement.

Depuis la racine du projet (`C:\\Users\\ASUS\\Intelligent-Traffic-Management-Luxembourg`) :

```
python -m pytest tests\\test_xai_shap.py tests\\test_xai_shap_stability.py tests\\test_xai_shap_figures.py tests\\test_xai_shap_multi_decision.py -v -ra
python -m agents.xai.shap_multi_decision --out docs\\shap_multi_decision_v2
```

Le dossier de sortie ne doit pas exister (code de sortie 2 sinon) ; si un contrôle du protocole échoue,
rien n'est écrit (code 1). Contenu produit :

| Fichier | Contenu |
|---|---|
| `cases.csv` | chaque décision retenue et son état |
| `exclusions.csv` | chaque ligne exclue et son motif |
| `per_state.csv` / `per_state.json` | contributions des fonds A, B, C et mesures, par état distinct |
| `summary.json` | protocole, entrées (SHA-256), exclusions, agrégats |
| `REPORT.md` | rapport lisible |

Séparateur CSV : `;` (comme les journaux du projet), encodage UTF-8.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Multi-decision SHAP stability study (read-only, never overwrites).")
    ap.add_argument("--out", required=True, help="new output folder (must not exist)")
    ap.add_argument("--runs", nargs="*", default=None, help="run folders (default: every S3 run in app_runs)")
    ap.add_argument("--qtable", default=str(sx.DEFAULT_QTABLE))
    a = ap.parse_args(argv)
    out = Path(a.out)
    if not out.is_absolute():
        out = sx.PROJECT_ROOT / out
    if out.exists():
        print(f"REFUSED: {out} already exists (results are never overwritten). Choose a new folder.", file=sys.stderr)
        return 2
    try:
        r = study(a.runs, Path(a.qtable))
    except (StudyError, sx.ExplanationError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1
    write_outputs(out, r)
    T = r["summary"]["total"]
    print(f"{r['decisions_included']} decisions -> {T['states']} distinct states; "
          f"stable {T['unweighted']['stable']}, partial {T['unweighted']['partial']}, unstable {T['unweighted']['unstable']}, "
          f"non evaluable {T['unweighted']['non_evaluable']}; reading: {T['reading']}")
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
