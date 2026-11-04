"""Run one strategy on the Kirchberg scenario for several seeds (SIMULATED results).

    python scripts/simulation/run_experiment.py --strategy S0_fixed_time --scale 5 --seeds 1 2 3
    python scripts/simulation/run_experiment.py --strategy S3_rl_qlearning --scale 5 --seeds 1 2 3 \
        --qtable sumo/lust_4_intersections/output/experiments_v1/rl/qtable_v4_FROZEN_ep26_eval.json

Each run goes to sumo/lust_4_intersections/output/experiments_<tag>/runs/<strategy>_x<scale>_seed<n>/
and is never overwritten (an existing run folder is skipped)."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agents.orchestrator import STRATEGIES, Incident, make_controller, run_episode  # noqa: E402

EXP = ROOT / "sumo" / "lust_4_intersections" / "output"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=STRATEGIES)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--seeds", type=int, nargs="+", default=[1])
    p.add_argument("--tag", default="v1")
    p.add_argument("--qtable", type=Path, default=EXP / "experiments_v1" / "rl" / "qtable_v4_FROZEN_ep26_eval.json")
    p.add_argument("--incident-lane", default=None, help="lane closed during the incident; use --incident-lane=<id> (ids start with '-')")
    p.add_argument("--incident-start", type=float, default=26400.0)
    p.add_argument("--incident-end", type=float, default=27600.0)
    p.add_argument("--incident-speed", type=float, default=0.05)
    p.add_argument("--incident-tag", default="incident")
    p.add_argument("--gui", action="store_true")
    p.add_argument("--gui-delay", type=float, default=100.0, help="ms per simulation step in sumo-gui (100 = 1 h in ~6 min)")
    p.add_argument("--progress", type=float, default=None, help="print a status line every N simulated seconds")
    p.add_argument("--no-forecast", action="store_true", help="do not pass the cascade forecasts to the decision agent")
    p.add_argument("--emergency-at", type=float, default=None, help="insert an ambulance on the avenue at this time (s)")
    p.add_argument("--emergency-priority", action="store_true", help="enable the emergency-priority module")
    p.add_argument("--detection-gate", action="store_true", help="detection: gate the congestion rule with the forecast")
    p.add_argument("--end", type=float, default=28800.0)
    a = p.parse_args(argv)
    for seed in a.seeds:
        name = f"{a.strategy}_x{a.scale:g}_seed{seed}" + (f"_{a.incident_tag}" if a.incident_lane else "") + \
            ("_noforecast" if a.no_forecast else "") + \
            (f"_ev{int(a.emergency_at)}{'_prio' if a.emergency_priority else ''}" if a.emergency_at else "")
        out = EXP / f"experiments_{a.tag}" / "runs" / name
        if (out / "kpis.json").exists():
            print(f"skip {name}: already done ({out})")
            continue
        inc = Incident(a.incident_lane, a.incident_start, a.incident_end, a.incident_speed) if a.incident_lane else None
        ctrl = make_controller(a.strategy, qtable=a.qtable)
        k = run_episode(a.strategy, a.scale, seed, out, controller=ctrl, incident=inc, gui=a.gui, end=a.end,
                        gui_delay_ms=a.gui_delay if a.gui else 0.0, progress_every=a.progress or (60.0 if a.gui else None),
                        use_forecast=not a.no_forecast, detection_gate=a.detection_gate,
                        emergency_at=a.emergency_at, emergency_priority=a.emergency_priority)
        print(f"{name}: arrived {k.get('arrived')} / inserted {k.get('inserted')} | travel {k.get('avg_travel_time_s')} s | "
              f"waiting {k.get('avg_waiting_time_s')} s | queue {k.get('avg_queue_veh')} veh | CO2 {k.get('co2_kg')} kg | "
              f"backlog {k.get('waiting_insertion_at_end')} | {k['wall_clock_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
