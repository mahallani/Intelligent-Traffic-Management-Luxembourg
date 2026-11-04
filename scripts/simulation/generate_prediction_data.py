"""Generate SIMULATED episodes for the cascade prediction (training and test sets kept apart by seed).

    python scripts/simulation/generate_prediction_data.py --set train     # seeds 201-203
    python scripts/simulation/generate_prediction_data.py --set test      # seeds 301-302

Each episode = one SUMO hour (07:00-08:00) with controller S0 or S2 and demand scale 1..6 (diversity of
congestion levels). The 5-s queue samples are in <run>/queue_timeseries.csv. Existing runs are skipped."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.orchestrator import run_episode  # noqa: E402

OUT = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "prediction_data"
SETS = {"train": {"seeds": [201, 202, 203], "scales": [1, 2, 3, 4, 5, 6]},
        "test": {"seeds": [301, 302], "scales": [1, 3, 5]},
        # final hold-out: seeds never used to train, select or tune anything; includes S1 (controller unseen in training)
        "holdout": {"seeds": [401, 402], "scales": [1, 2, 3, 4, 5, 6]}}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=SETS, required=True)
    p.add_argument("--strategies", nargs="+", default=None)
    a = p.parse_args(argv)
    cfg = SETS[a.set]
    strategies = a.strategies or (["S0_fixed_time", "S1_actuated", "S2_demand_gap"] if a.set == "holdout"
                                  else ["S0_fixed_time", "S2_demand_gap"])
    for strat in strategies:
        for scale in cfg["scales"]:
            for seed in cfg["seeds"]:
                out = OUT / a.set / f"{strat}_x{scale}_seed{seed}"
                if (out / "kpis.json").exists():
                    continue
                k = run_episode(strat, float(scale), seed, out)
                print(f"{a.set} {strat} x{scale} seed{seed}: avg queue {k.get('avg_queue_veh')} veh, {k['wall_clock_s']} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
