"""Train the cascade prediction on TRAINING episodes and evaluate it on TEST episodes (different seeds),
horizon by horizon, against persistence, the historical profile and direct (non-cascade) models.

    python scripts/simulation/train_eval_cascade.py --tag v1

Outputs (never overwritten) in sumo/lust_4_intersections/output/experiments_v1/prediction/:
  cascade_model_<tag>.json, cascade_predictions_test_<tag>.csv (prediction, observed, error),
  cascade_metrics_<tag>.csv, cascade_report_<tag>.json. All data are SIMULATED."""
import argparse
import csv
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents import DATA_ORIGIN  # noqa: E402
from agents.prediction.cascade import HORIZONS, episode_samples, fit  # noqa: E402

BASE = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1"
DATA = BASE / "prediction_data"
OUT = BASE / "prediction"
METHODS = ("cascade", "direct", "persistence", "profile")


def load(split):
    eps = []
    for d in sorted((DATA / split).iterdir()):
        if "INCOMPLETE" in d.name or not (d / "kpis.json").exists():
            continue
        with open(d / "queue_timeseries.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        eps.append((d.name, episode_samples(rows)))
    return eps


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v2")
    p.add_argument("--transform", choices=["none", "log1p"], default=None,
                   help="default: chosen on the validation split (train seeds 201-202 -> 203)")
    a = p.parse_args(argv)
    files = {k: OUT / f"{k}_{a.tag}.{ext}" for k, ext in (("cascade_model", "json"), ("cascade_predictions_test", "csv"),
                                                           ("cascade_metrics", "csv"), ("cascade_report", "json"))}
    for f in files.values():
        if f.exists():
            sys.exit(f"{f} exists - use another --tag")
    OUT.mkdir(parents=True, exist_ok=True)
    train, test = load("train"), load("test")
    seeds_train = {n.split("seed")[-1] for n, _ in train}
    seeds_test = {n.split("seed")[-1] for n, _ in test}
    assert not seeds_train & seeds_test, "train/test seeds overlap"
    # ---- model selection on a VALIDATION split of the training seeds only (test seeds never used here)
    fit_eps = [s for n, s in train if not n.endswith("seed203")]
    val_eps = [s for n, s in train if n.endswith("seed203")]
    validation = {}
    for kind in ("none", "log1p"):
        mv = fit(fit_eps, transform=kind)
        validation[kind] = {h // 60: round(st.mean(abs(mv.predict(r["x"])[h] - r["y"][h]) for e in val_eps for r in e), 3)
                            for h in HORIZONS}
    validation["persistence"] = {h // 60: round(st.mean(abs(r["x"][0] - r["y"][h]) for e in val_eps for r in e), 3)
                                 for h in HORIZONS}
    chosen = a.transform or min(("none", "log1p"), key=lambda k: sum(validation[k].values()))
    print("validation MAE (train seeds 201-202 -> 203):", validation, "-> chosen:", chosen)
    model = fit([s for _, s in train], transform=chosen)
    model.meta["validation_mae"] = validation
    model.meta.update({"train_episodes": [n for n, _ in train], "test_episodes": [n for n, _ in test],
                       "data_origin": DATA_ORIGIN})
    model.save(files["cascade_model"])
    preds = []
    for name, samples in test:
        strat, scale = name.split("_x")[0], name.split("_x")[1].split("_")[0]
        for s in samples:
            c, d = model.predict(s["x"]), model.predict_direct(s["x"])
            pr = model.predict_profile(s["tls"], s["minute"])
            for h in HORIZONS:
                obs = s["y"][h]
                row = {"episode": name, "strategy": strat, "scale": scale, "origin_s": s["origin"], "tls": s["tls"],
                       "horizon_min": h // 60, "observed": round(obs, 3), "cascade": round(c[h], 3), "direct": round(d[h], 3),
                       "persistence": round(s["x"][0], 3), "profile": round(pr[h], 3) if pr[h] is not None else ""}
                for mth in METHODS:
                    row[f"err_{mth}"] = round(row[mth] - obs, 3) if row[mth] != "" else ""
                row["data_origin"] = DATA_ORIGIN
                preds.append(row)
    with open(files["cascade_predictions_test"], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(preds[0]), delimiter=";")
        w.writeheader()
        w.writerows(preds)
    metrics = []

    def add(group, sel):
        for h in HORIZONS:
            rows = [r for r in sel if r["horizon_min"] == h // 60]
            m = {"group": group, "horizon_min": h // 60, "n": len(rows)}
            for mth in METHODS:
                e = [r[f"err_{mth}"] for r in rows if r[f"err_{mth}"] != ""]
                m[f"MAE_{mth}"] = round(st.mean(abs(x) for x in e), 3) if e else None
                m[f"RMSE_{mth}"] = round(math.sqrt(st.mean(x * x for x in e)), 3) if e else None
            m["skill_cascade_vs_persistence"] = round(1 - m["MAE_cascade"] / m["MAE_persistence"], 3) if m["MAE_persistence"] else None
            metrics.append(m)
    add("all_test", preds)
    for sc in sorted({r["scale"] for r in preds}, key=float):
        add(f"scale_x{sc}", [r for r in preds if r["scale"] == sc])
    for strat in sorted({r["strategy"] for r in preds}):
        add(strat, [r for r in preds if r["strategy"] == strat])
    with open(files["cascade_metrics"], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(metrics[0]), delimiter=";")
        w.writeheader()
        w.writerows(metrics)
    rep = {"model": model.meta, "metrics_all_test": [m for m in metrics if m["group"] == "all_test"],
           "split": {"train_seeds": sorted(seeds_train), "test_seeds": sorted(seeds_test)},
           "leakage_controls": ["train and test episodes use disjoint SUMO seeds", "features use only past samples",
                                "later cascade stages trained on out-of-fold earlier-stage predictions (folds = episodes)"],
           "data_origin": DATA_ORIGIN}
    files["cascade_report"].write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for m in metrics:
        print(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
