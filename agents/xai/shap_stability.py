"""Sensitivity of the exact SHAP explanation to the WEIGHTS of the background (2026-10-29) - OFFLINE, READ-ONLY.

Same decision, same frozen Q-table, same output (delta = Q(passer) - Q(garder)), same signal and green phase, and
EXACTLY the same retained background states; only the weights change:
    method A ("visits")  : weight = number of visits of the state in the table (current method of shap_qtable.py)
    method B ("uniform") : weight = 1 for every retained state

Retained states = the states returned by shap_qtable.background_for() for which ALL 2^4 hybrid states exist in the
table, i.e. the exclusion rule of shap_qtable.exact_shapley_delta(). This module recomputes that set explicitly and
then CHECKS it against shap_qtable: (1) the number of retained states must be equal, (2) the explanation computed with
the filtered set and visit weights must be identical to the default explanation of shap_qtable (same phi, same base).
If a check fails, nothing is written.

    python -m agents.xai.shap_stability --out docs/shap_stability_v1        (from the project root)

shap_qtable.py, the Q-table and the run logs are only read. The output folder must not exist (nothing is overwritten).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from . import shap_qtable as sx

SIGN_TOL = 1e-12          # |phi| <= SIGN_TOL is reported as sign "0"
MATCH_TOL = 1e-12         # filtered-background explanation vs default explanation of shap_qtable


def retained_background(table: sx.QTable, tls: str, g: int, x, background=None) -> list:
    """Background states (with their visit weights) for which every hybrid state exists in the table.
    Same rule as shap_qtable.exact_shapley_delta(): one missing hybrid excludes the whole background state."""
    x = tuple(int(v) for v in x)
    bg = background if background is not None else sx.background_for(table, tls, g)
    out = []
    for b, w in bg:
        b = tuple(int(v) for v in b)
        if all(table.has(sx.make_key(tls, g, [x[i] if S[i] else b[i] for i in range(len(x))]))
               for S in itertools.product((0, 1), repeat=len(x))):
            out.append((b, float(w)))
    return out


def sign(v: float) -> str:
    return "0" if abs(v) <= SIGN_TOL else ("+" if v > 0 else "-")


def ranks_by_abs(phi) -> list:
    """Competition ranking by |phi| (1 = largest); exact ties share the best rank (e.g. 1, 2, 2, 4)."""
    a = [abs(v) for v in phi]
    return [1 + sum(1 for o in a if o > v + SIGN_TOL) for v in a]


def compare_weightings(table: sx.QTable, tls: str, g: int, x) -> dict:
    x = tuple(int(v) for v in x)
    full = sx.background_for(table, tls, g)
    kept = retained_background(table, tls, g, x, full)
    default = sx.exact_shapley_delta(table, tls, g, x)                       # current explanation (method A, unfiltered input)
    if len(kept) != default.background_retained:
        raise sx.ExplanationError(f"retained set mismatch: {len(kept)} here vs {default.background_retained} in shap_qtable")
    res_a = sx.exact_shapley_delta(table, tls, g, x, background=kept)
    if res_a.background_excluded != 0:
        raise sx.ExplanationError("a retained state was excluded again: inconsistent retained set")
    if any(abs(p - q) > MATCH_TOL for p, q in zip(res_a.phi, default.phi)) or abs(res_a.base - default.base) > MATCH_TOL:
        raise sx.ExplanationError("filtered background (visit weights) does not reproduce the default explanation")
    uniform = [(b, 1.0) for b, _ in kept]
    res_b = sx.exact_shapley_delta(table, tls, g, x, background=uniform)
    if res_b.background_excluded != 0 or res_b.background_retained != len(kept):
        raise sx.ExplanationError("uniform method did not use exactly the retained states")
    if [b for b, _ in uniform] != [b for b, _ in kept]:
        raise sx.ExplanationError("uniform and visit-weighted backgrounds differ")
    if abs(res_a.delta_x - res_b.delta_x) > 0:
        raise sx.ExplanationError("the explained delta differs between the two methods")
    ra, rb = ranks_by_abs(res_a.phi), ranks_by_abs(res_b.phi)
    rows = []
    for i, f in enumerate(sx.FEATURES):
        rows.append({"variable": f, "label": sx.FEATURE_LABELS[f], "class": sx.CLASS_LABELS[f][x[i]],
                     "shap_visits": res_a.phi[i], "shap_uniform": res_b.phi[i],
                     "abs_difference": abs(res_a.phi[i] - res_b.phi[i]),
                     "sign_visits": sign(res_a.phi[i]), "sign_uniform": sign(res_b.phi[i]),
                     "rank_visits": ra[i], "rank_uniform": rb[i],
                     "constant_in_retained_background": i in res_a.constant_variables,
                     "retained_classes": {sx.CLASS_LABELS[f][c]: {"visits_weight": res_a.retained_class_weights[i][c],
                                                                  "uniform_count": res_b.retained_class_weights[i][c]}
                                          for c in sorted(res_a.retained_class_weights[i])}})
    informative = [r for r in rows if not r["constant_in_retained_background"]]
    same_signs = all(r["sign_visits"] == r["sign_uniform"] for r in rows)
    same_ranks = ra == rb
    max_diff = max(r["abs_difference"] for r in rows)
    sum_abs_a = sum(abs(v) for v in res_a.phi)
    unreliable_states = sum(1 for b, _ in kept if not table.reliable(sx.make_key(tls, g, b)))
    return {
        "tls": tls, "green_phase_index": g, "state": list(x), "delta": res_a.delta_x,
        "background": {"states_total": len(full), "states_retained": len(kept), "states_excluded": len(full) - len(kept),
                       "retained_states": [{"state": list(b), "visits_weight": w,
                                            "reliable": table.reliable(sx.make_key(tls, g, b))} for b, w in kept],
                       "visit_weight_retained": sum(w for _, w in kept), "retained_states_unreliable": unreliable_states},
        "methods": {
            "visits": {"base_value": res_a.base, "sum_contributions": res_a.sum_phi, "additivity_error": res_a.additivity_error,
                       "weighted_share_unreliable_evaluations": res_a.weighted_share_unreliable,
                       "reproduces_shap_qtable_default": True},
            "uniform": {"base_value": res_b.base, "sum_contributions": res_b.sum_phi, "additivity_error": res_b.additivity_error,
                        "weighted_share_unreliable_evaluations": res_b.weighted_share_unreliable}},
        "comparison": rows,
        "summary": {"same_signs_all_variables": same_signs, "same_ranking": same_ranks,
                    "same_signs_informative_variables": all(r["sign_visits"] == r["sign_uniform"] for r in informative),
                    "max_abs_difference": max_diff,
                    "max_abs_difference_relative_to_sum_abs_visits": (max_diff / sum_abs_a) if sum_abs_a else None,
                    "base_value_difference": res_b.base - res_a.base,
                    "additivity_tolerance": sx.ADDITIVITY_TOL,
                    "additivity_ok_both": res_a.additivity_error <= sx.ADDITIVITY_TOL and res_b.additivity_error <= sx.ADDITIVITY_TOL},
    }


def conclusion(cmp: dict) -> str:
    """Rule fixed before looking at the numbers: 'stable in sign and ranking' if all signs and the ranking by |phi|
    are identical; otherwise 'sensitive'. Magnitudes are always reported, never hidden behind the verdict."""
    s = cmp["summary"]
    if s["same_signs_all_variables"] and s["same_ranking"]:
        return ("Relativement stable en signe et en classement : les deux pondérations donnent les mêmes signes et le même "
                f"ordre des variables ; l'écart maximal d'une contribution est {s['max_abs_difference']:.6f}.")
    parts = []
    if not s["same_signs_all_variables"]:
        parts.append("au moins un signe change")
    if not s["same_ranking"]:
        parts.append("le classement des variables change")
    return f"Sensible à la pondération : {' et '.join(parts)} (écart maximal {s['max_abs_difference']:.6f})."


def run(run_dir=sx.DEFAULT_RUN, tls=sx.DEFAULT_TLS, time_s=sx.DEFAULT_TIME_S, qtable_path=sx.DEFAULT_QTABLE) -> dict:
    row = sx.read_decision(Path(run_dir) / "decisions.csv", tls, time_s)
    ex = sx.check_learned_decision(row)
    table = sx.load_qtable(qtable_path)
    key = sx.state_key_from_explanation(tls, ex)
    logged = sx.verify_logged_values(table, key, ex)
    _, g, x = sx.parse_key(key)
    cmp = compare_weightings(table, tls, g, x)
    if abs(cmp["delta"] - logged["delta"]) > 1e-12:
        raise sx.ExplanationError("delta differs from the verified logged decision")
    return {
        "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
        "question": "Do the exact SHAP values change when only the background weights change (visits vs uniform)?",
        "model": {"file": sx._rel(qtable_path), "type": "tabular Q-learning (S3), frozen table"},
        "explained_output": "delta = Q(passer) - Q(garder)",
        "decision": {"run": sx._rel(run_dir), "tls": tls, "time_s": float(row["time_s"]), "clock": sx._clock(float(row["time_s"])),
                     "source": ex["source"], "q_garder": logged["q_garder"], "q_passer": logged["q_passer"],
                     "visits_garder_passer": logged["visits_garder_passer"]},
        **cmp,
        "conclusion": conclusion(cmp),
        "limitations": [
            "Only the weights of the SAME 29 retained states change; other backgrounds (other runs, other demand) are not tested.",
            "A variable that is constant in the retained background gets 0 in both methods by construction: this proves nothing about its effect.",
            "Many retained states are unreliable (fewer than 3 visits); uniform weights give them more influence than visit weights.",
            "SHAP describes the output of the table, not a causal effect on traffic. One decision only.",
        ],
    }


def to_markdown(r: dict) -> str:
    d, s, m = r["decision"], r["summary"], r["methods"]
    L = [f"# Sensibilité de l'explication SHAP à la pondération du fond – S3, {d['clock']}, feu {d['tls']} – SIMULÉ", "",
         f"- Décision : run `{Path(d['run']).name}`, source « {d['source']} » ; Q(garder) = {d['q_garder']:.6f}, "
         f"Q(passer) = {d['q_passer']:.6f}, Δ = {r['delta']:.6f}",
         f"- Fond : {r['background']['states_total']} états, **{r['background']['states_retained']} retenus** (mêmes états pour A et B), "
         f"{r['background']['states_excluded']} exclus ; poids de visites retenu = {r['background']['visit_weight_retained']:g} ; "
         f"{r['background']['retained_states_unreliable']} états retenus peu fiables", "",
         "| Variable | Classe | A : poids = visites | B : poids uniforme | Écart absolu | Signe A / B | Rang A / B |",
         "|---|---|---|---|---|---|---|"]
    for c in r["comparison"]:
        flag = " (*)" if c["constant_in_retained_background"] else ""
        L.append(f"| {c['label']}{flag} | {c['class']} | {c['shap_visits']:+.6f} | {c['shap_uniform']:+.6f} | {c['abs_difference']:.6f} | "
                 f"{c['sign_visits']} / {c['sign_uniform']} | {c['rank_visits']} / {c['rank_uniform']} |")
    L += ["", "(*) constante dans le fond retenu : 0 par construction dans les deux méthodes, ce n'est pas la preuve d'une absence d'effet.", "",
          "| | A : visites | B : uniforme |", "|---|---|---|",
          f"| Valeur de référence | {m['visits']['base_value']:+.6f} | {m['uniform']['base_value']:+.6f} |",
          f"| Somme des contributions | {m['visits']['sum_contributions']:+.6f} | {m['uniform']['sum_contributions']:+.6f} |",
          f"| Référence + somme | {m['visits']['base_value'] + m['visits']['sum_contributions']:+.6f} | {m['uniform']['base_value'] + m['uniform']['sum_contributions']:+.6f} |",
          f"| Δ expliqué | {r['delta']:+.6f} | {r['delta']:+.6f} |",
          f"| Erreur d'additivité | {m['visits']['additivity_error']:.2e} | {m['uniform']['additivity_error']:.2e} |",
          f"| Part pondérée d'évaluations peu fiables | {100 * m['visits']['weighted_share_unreliable_evaluations']:.1f} % | {100 * m['uniform']['weighted_share_unreliable_evaluations']:.1f} % |",
          "", f"- Mêmes signes : {s['same_signs_all_variables']} ; même classement : {s['same_ranking']} ; écart maximal : {s['max_abs_difference']:.6f} "
          f"({100 * s['max_abs_difference_relative_to_sum_abs_visits']:.1f} % de la somme des |contributions| de A)",
          f"- Contrôles : l'ensemble retenu reproduit exactement l'explication par défaut de `shap_qtable` ; additivité ≤ {s['additivity_tolerance']:.0e} dans les deux méthodes : {s['additivity_ok_both']}",
          "", f"**Conclusion :** {r['conclusion']}", "", "## Limites", ""]
    L += [f"- {x}" for x in r["limitations"]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SHAP sensitivity to the background weights (visits vs uniform)")
    p.add_argument("--run", type=Path, default=sx.DEFAULT_RUN)
    p.add_argument("--tls", default=sx.DEFAULT_TLS)
    p.add_argument("--time", type=float, default=sx.DEFAULT_TIME_S)
    p.add_argument("--qtable", type=Path, default=sx.DEFAULT_QTABLE)
    p.add_argument("--out", type=Path, required=True, help="NEW folder (refused if it already exists)")
    a = p.parse_args(argv)
    if a.out.exists():
        print(f"refused: {a.out} already exists (nothing is overwritten)", file=sys.stderr)
        return 2
    try:
        r = run(a.run, a.tls, a.time, a.qtable)
    except sx.ExplanationError as e:
        print(f"NO RESULT WRITTEN - check failed: {e}", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True)
    (a.out / "shap_stability.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "shap_stability.md").write_text(to_markdown(r), encoding="utf-8")
    print(to_markdown(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
