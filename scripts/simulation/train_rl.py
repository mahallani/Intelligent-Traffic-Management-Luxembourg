"""Train the Q-learning signal agent (S3) in SUMO - resumable, a few episodes per call.

    python scripts/simulation/train_rl.py --episodes 5 --scale 5

Episode k uses SUMO seed 100+k (training seeds 101, 102, ...; evaluation uses seeds 1-3, never
seen in training). The Q-table and a training log are written to
sumo/lust_4_intersections/output/experiments_v1/rl/. The Q-table file is updated after every
episode (atomic replace); the log is append-only (one row per episode).
v1 (qtable_v1.json, training_log_v1.csv, training/) = first attempt, kept for traceability: its greedy
policy picked untried actions (Q=0 > negative values) and performed worse than fixed time.
v2 (qtable_v2.json ...) = visit-count rule added, reward = halted vehicles at the next decision only
(not semi-Markov): 15 episodes, no improvement over fixed time. v3 = semi-Markov reward, fallback =
programmed duration: 8 episodes, no improvement. v4 = semi-Markov reward + fallback = demand-gap rule."""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.decision.controllers import QLearningController  # noqa: E402
from agents.orchestrator import run_episode  # noqa: E402

RL = ROOT / "sumo" / "lust_4_intersections" / "output" / "experiments_v1" / "rl"
LOG_COLS = ["episode", "seed", "scale", "epsilon", "q_states", "decisions", "explorations", "fallback_decisions", "updates", "arrived",
            "avg_travel_time_s", "avg_waiting_time_s", "avg_queue_veh", "total_time_loss_all_h", "co2_kg",
            "forced_max_green", "wall_clock_s"]


def epsilon(ep: int) -> float:
    return max(0.02, 0.3 * 0.85 ** (ep - 1))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, default=5)
    p.add_argument("--scale", type=float, default=5.0)
    p.add_argument("--qtable", type=Path, default=RL / "qtable_v4.json")
    p.add_argument("--log-name", default="training_log_v4.csv")
    p.add_argument("--train-dir", default="training_v4")
    a = p.parse_args(argv)
    log = RL / a.log_name
    for _ in range(a.episodes):
        ctrl = QLearningController(qtable_path=a.qtable, train=True)
        ep = ctrl.meta["episodes_trained"] + 1
        seed = 100 + ep
        ctrl.rng.seed(seed)
        ctrl.eps = epsilon(ep)
        out = RL / a.train_dir / f"ep{ep:03d}_seed{seed}"
        k = run_episode("S3_rl_qlearning", a.scale, seed, out, controller=ctrl)
        ctrl.save(a.qtable, seed, a.scale)
        row = {"episode": ep, "seed": seed, "scale": a.scale, "epsilon": round(ctrl.eps, 3), "q_states": len(ctrl.q),
               **{c: ctrl.stats[c] for c in ("decisions", "explorations", "fallback_decisions", "updates")},
               **{c: k.get(c) for c in ("arrived", "avg_travel_time_s", "avg_waiting_time_s", "avg_queue_veh",
                                        "total_time_loss_all_h", "co2_kg", "wall_clock_s")},
               "forced_max_green": k["actuator"]["forced_max_green"]}
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_COLS, delimiter=";")
            if new:
                w.writeheader()
            w.writerow(row)
        print(row, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
