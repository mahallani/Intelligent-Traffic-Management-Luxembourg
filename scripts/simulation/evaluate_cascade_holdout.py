"""Final evaluation of the FROZEN cascade model (cascade_model_v2.json) on the hold-out episodes
(seeds 401-402, never used to train, select or tune anything; controller S1 never seen in training).

    python scripts/simulation/evaluate_cascade_holdout.py --tag holdout_v1

Compared per horizon (+5/+10/+15 min): cascade, direct models, persistence, historical profile.
Groups: all, demand scale, controller, congestion state at the forecast origin (current halted vehicles at
the signal: free < 2, moderate 2-10, congested > 10). 95 % confidence interval of the MAE difference
cascade - baseline by paired bootstrap over EPISODES (1000 resamples, seed 0).
Outputs (never overwritten) in .../experiments_v1/prediction/. SIMULATED data only."""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.prediction.cascade import HORIZONS, CascadeModel, episode_samples  # noqa: E402

BASE = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1"
METHODS = ("cascade", "direct", "persistence", "profile")


def state(v):
    return "free" if v < 2 else "moderate" if v <= 10 else "congested"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="holdout_v1")
    p.add_argument("--model", type=Path, default=BASE / "prediction" / "cascade_model_v2.json")
    a = p.parse_args(argv)
    out_rows = BASE / "prediction" / f"cascade_predictions_{a.tag}.csv"
    out_met = BASE / "prediction" / f"cascade_metrics_{a.tag}.csv"
    out_json = BASE / "prediction" / f"cascade_report_{a.tag}.json"
    for f in (out_rows, out_met, out_json):
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    model = CascadeModel.load(a.model)
    used = {n.split("seed")[-1] for n in model.meta["train_episodes"] + model.meta["test_episodes"]} | {"203", "50", "60", "61"}
    rows = []
    for d in sorted((BASE / "prediction_data" / "holdout").iterdir()):
        if "INCOMPLETE" in d.name or not (d / "kpis.json").exists():
            continue
        assert d.name.split("seed")[-1] not in used, f"seed of {d.name} was used before"
        with open(d / "queue_timeseries.csv", encoding="utf-8") as fh:
            samples = episode_samples(list(csv.DictReader(fh, delimiter=";")))
        strat, scale = d.name.split("_x")[0], d.name.split("_x")[1].split("_")[0]
        for s in samples:
            c, dr, pr = model.predict(s["x"]), model.predict_direct(s["x"]), model.predict_profile(s["tls"], s["minute"])
            for h in HORIZONS:
                r = {"episode": d.name, "strategy": strat, "scale": scale, "origin_s": s["origin"], "tls": s["tls"],
                     "horizon_min": h // 60, "state_at_origin": state(s["x"][0]), "observed": s["y"][h],
                     "cascade": c[h], "direct": dr[h], "persistence": s["x"][0], "profile": pr[h]}
                rows.append(r)
    with open(out_rows, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) + ["data_origin"], delimiter=";")
        w.writeheader()
        w.writerows({**{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, "data_origin": DATA_ORIGIN} for r in rows)
    rng = np.random.default_rng(0)
    metrics = []

    def evaluate(group, sel):
        eps = sorted({r["episode"] for r in sel})
        for h in HORIZONS:
            rs = [r for r in sel if r["horizon_min"] == h // 60]
            if not rs:
                continue
            m = {"group": group, "horizon_min": h // 60, "n": len(rs), "episodes": len(eps)}
            for mth in METHODS:
                m[f"MAE_{mth}"] = round(float(np.mean([abs(r[mth] - r["observed"]) for r in rs])), 3)
            by_ep = {e: [r for r in rs if r["episode"] == e] for e in eps}
            for base in ("persistence", "profile"):
                diffs = []
                for _ in range(1000):
                    pick = rng.choice(eps, size=len(eps), replace=True)
                    sub = [r for e in pick for r in by_ep[e]]
                    diffs.append(np.mean([abs(r["cascade"] - r["observed"]) - abs(r[base] - r["observed"]) for r in sub]))
                lo, hi = np.percentile(diffs, [2.5, 97.5])
                m[f"diff_vs_{base}_CI95"] = f"[{lo:.3f}; {hi:.3f}]"
                m[f"cascade_better_than_{base}"] = bool(hi < 0)
            metrics.append(m)
    evaluate("all_holdout", rows)
    for sc in sorted({r["scale"] for r in rows}, key=float):
        evaluate(f"scale_x{sc}", [r for r in rows if r["scale"] == sc])
    for st_ in ("free", "moderate", "congested"):
        evaluate(f"state_{st_}", [r for r in rows if r["state_at_origin"] == st_])
    for strat in sorted({r["strategy"] for r in rows}):
        evaluate(f"controller_{strat}", [r for r in rows if r["strategy"] == strat])
    with open(out_met, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(metrics[0]), delimiter=";")
        w.writeheader()
        w.writerows(metrics)
    out_json.write_text(json.dumps({"model": a.model.name, "holdout_seeds": [401, 402], "seeds_excluded": sorted(used),
                                    "n_predictions": len(rows), "metrics": metrics, "data_origin": DATA_ORIGIN}, indent=1),
                        encoding="utf-8")
    for m in metrics:
        print({k: m[k] for k in ("group", "horizon_min", "n", "MAE_cascade", "MAE_direct", "MAE_persistence", "MAE_profile",
                                 "cascade_better_than_persistence", "cascade_better_than_profile")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
