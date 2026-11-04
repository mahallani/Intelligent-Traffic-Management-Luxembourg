"""Read-only computations supporting the scientific review of the XAI (SHAP) part.

Nothing here changes the project: it only READS the frozen Q-table, the decision logs and the existing reports,
and reuses the functions of agents/xai/shap_qtable.py and agents/xai/shap_stability.py without modifying them.

What it computes (written to review_computations.json next to this file, only if that file does not exist):
  1. per_background_decomposition: exact SHAP is linear in the background weights, so
         phi_i(A) = sum_b w_b * phi_i(b) / sum_b w_b      (w_b = visits)
         phi_i(B) = mean_b phi_i(b)                        (uniform)
     where phi_i(b) is the exact SHAP value computed with the single background state b.
     The script checks that this reproduces the two published explanations, then splits the contribution of
     file_autre by the file_autre class of b and by the reliability of b.
  2. file_autre_slice: delta(file_servie=0, file_autre=c, en_mouvement=0, durée_vert=0) for every class c
     (the other variables fixed at the explained state), with visits and reliability.
  3. unreliable_causes: why each retained background state is "unreliable" (fewer than 3 tries of one action,
     or equal Q-values).
  4. validation_candidates: how many logged decisions of the S3 runs could be explained (feasibility only:
     no explanation is computed for them here).

Run from the project root (the JSON of this folder already exists and is never overwritten, so give a new file):
    python docs/shap_scientific_review_v1/review_computations.py docs/shap_scientific_review_v1/review_computations_rerun.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.xai import shap_qtable as sx          # noqa: E402
from agents.xai import shap_stability as ss       # noqa: E402

OUT = Path(__file__).resolve().parent / "review_computations.json"
STABILITY = ROOT / "docs" / "shap_stability_v2" / "shap_stability.json"
TOL = 1e-12


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0]) if argv else OUT
    if out.exists():
        print(f"REFUSED: {out} already exists (never overwritten).", file=sys.stderr)
        return 2
    inputs = [sx.DEFAULT_QTABLE, sx.DEFAULT_RUN / "decisions.csv", STABILITY]
    before = {sx._rel(p): (sha(p), p.stat().st_mtime_ns) for p in inputs}

    table = sx.load_qtable()
    stab = json.loads(STABILITY.read_text(encoding="utf-8"))
    tls, g, x = stab["tls"], int(stab["green_phase_index"]), tuple(stab["state"])
    kept = ss.retained_background(table, tls, g, x)
    if len(kept) != stab["background"]["states_retained"]:
        raise SystemExit("retained background differs from the stability report")

    # 1. per-background decomposition ---------------------------------------------------------------
    per_b = []
    for b, w in kept:
        r = sx.exact_shapley_delta(table, tls, g, x, background=[(b, 1.0)])
        key = sx.make_key(tls, g, b)
        per_b.append({"state": list(b), "visits_weight": w, "reliable": table.reliable(key),
                      "delta_b": table.delta(key), "phi": list(r.phi)})
    W = sum(p["visits_weight"] for p in per_b)
    n = len(per_b)
    recon = {"visits": [sum(p["visits_weight"] * p["phi"][i] for p in per_b) / W for i in range(4)],
             "uniform": [sum(p["phi"][i] for p in per_b) / n for i in range(4)]}
    for m, key in (("visits", "shap_visits"), ("uniform", "shap_uniform")):
        for i, c in enumerate(stab["comparison"]):
            if abs(recon[m][i] - c[key]) > TOL:
                raise SystemExit(f"decomposition does not reproduce {m} {c['variable']}")
    base_recon = {"visits": sum(p["visits_weight"] * p["delta_b"] for p in per_b) / W,
                  "uniform": sum(p["delta_b"] for p in per_b) / n}

    fa = sx.FEATURES.index("file_autre")
    labels = sx.CLASS_LABELS["file_autre"]
    by_class = defaultdict(lambda: {"states": 0, "visits_weight": 0.0, "sum_w_phi": 0.0, "sum_phi": 0.0,
                                    "reliable_states": 0})
    by_rel = defaultdict(lambda: {"states": 0, "visits_weight": 0.0, "sum_w_phi": 0.0, "sum_phi": 0.0})
    for p in per_b:
        c = labels[p["state"][fa]]
        d = by_class[c]
        d["states"] += 1
        d["visits_weight"] += p["visits_weight"]
        d["sum_w_phi"] += p["visits_weight"] * p["phi"][fa]
        d["sum_phi"] += p["phi"][fa]
        d["reliable_states"] += int(p["reliable"])
        r = by_rel["reliable" if p["reliable"] else "unreliable"]
        r["states"] += 1
        r["visits_weight"] += p["visits_weight"]
        r["sum_w_phi"] += p["visits_weight"] * p["phi"][fa]
        r["sum_phi"] += p["phi"][fa]

    def share(d):
        return {"states": d["states"], "visits_weight": d["visits_weight"],
                **({"reliable_states": d["reliable_states"]} if "reliable_states" in d else {}),
                "weight_share_A": d["visits_weight"] / W, "weight_share_B": d["states"] / n,
                "contribution_to_phi_A": d["sum_w_phi"] / W, "contribution_to_phi_B": d["sum_phi"] / n,
                "mean_phi_b": d["sum_phi"] / d["states"]}
    file_autre_by_class = {c: share(by_class[c]) for c in labels if c in by_class}
    file_autre_by_reliability = {k: share(v) for k, v in by_rel.items()}

    # 2. slice over file_autre, other variables fixed at x ------------------------------------------
    slice_ = []
    for c in range(len(labels)):
        s = list(x)
        s[fa] = c
        key = sx.make_key(tls, g, s)
        slice_.append({"file_autre_class": labels[c], "state": s, "in_table": table.has(key),
                       "delta": table.delta(key) if table.has(key) else None,
                       "visits_garder_passer": table.visits(key) if table.has(key) else None,
                       "reliable": table.reliable(key)})

    # 3. causes of unreliability ---------------------------------------------------------------------
    causes = Counter()
    for p in per_b:
        if p["reliable"]:
            continue
        key = sx.make_key(tls, g, p["state"])
        v = table.visits(key)
        qk, qa = table.q[key]
        if min(v) < sx.MIN_VISITS and qk == qa:
            causes["fewer_than_3_tries_and_equal_q"] += 1
        elif min(v) < sx.MIN_VISITS:
            causes["fewer_than_3_tries_of_one_action"] += 1
        else:
            causes["equal_q_values_only"] += 1
    unrel_examples = [{"state": p["state"], "visits_weight": p["visits_weight"],
                       "visits_garder_passer": table.visits(sx.make_key(tls, g, p["state"]))}
                      for p in sorted(per_b, key=lambda p: -p["visits_weight"]) if not p["reliable"]][:6]

    # 4. feasibility of a multi-decision validation ----------------------------------------------------
    runs = sorted((sx.OUTPUT / "app_runs").glob("*_S3_rl_qlearning_*"))
    cand = []
    for run in runs:
        f = run / "decisions.csv"
        if not f.exists():
            continue
        with open(f, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        info = {"run": sx._rel(run), "rows": len(rows), "has_explanation_column": bool(rows) and "explanation" in rows[0],
                "reasons": dict(Counter(r.get("reason") for r in rows))}
        stats = Counter()
        states, per_tls = set(), Counter()
        if info["has_explanation_column"]:
            for r in rows:
                r = dict(r)
                r["explanation_json"] = json.loads(r["explanation"]) if r.get("explanation") else None
                try:
                    ex = sx.check_learned_decision(r)
                except sx.NotExplainable as e:
                    stats["not_learned:" + str(e).split(":")[0]] += 1
                    continue
                except sx.ExplanationError:
                    stats["inconsistent_log"] += 1
                    continue
                key = sx.state_key_from_explanation(r["tls"], ex)
                try:
                    sx.verify_logged_values(table, key, ex)
                except sx.ExplanationError as e:
                    stats["log_vs_table_mismatch"] += 1
                    continue
                stats["candidate_learned_and_verified"] += 1
                states.add(key)
                per_tls[r["tls"]] += 1
        info.update({"classification": dict(stats), "distinct_states": len(states), "candidates_per_tls": dict(per_tls)})
        cand.append(info)

    after = {sx._rel(p): (sha(p), p.stat().st_mtime_ns) for p in inputs}
    res = {
        "data_origin": "SIMULATED_sumo_lust_kirchberg_4tls",
        "inputs_sha256": {k: v[0] for k, v in before.items()},
        "inputs_unchanged": before == after,
        "decision": {"tls": tls, "green_phase_index": g, "state": list(x), "delta": stab["delta"]},
        "decomposition_reproduces_reports": True,
        "base_value_recomputed": base_recon,
        "file_autre_by_background_class": file_autre_by_class,
        "file_autre_by_background_reliability": file_autre_by_reliability,
        "file_autre_slice_other_variables_fixed": slice_,
        "unreliable_causes": dict(causes),
        "unreliable_heaviest_examples": unrel_examples,
        "per_background_state": per_b,
        "validation_candidates": cand,
    }
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("inputs_unchanged", "base_value_recomputed", "file_autre_by_background_class",
                                          "file_autre_by_background_reliability", "file_autre_slice_other_variables_fixed",
                                          "unreliable_causes", "unreliable_heaviest_examples", "validation_candidates")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
