"""Signal safety (yellow, min/max green, states from the program) for every adaptive strategy, and the
emergency-priority module tested on its own. Short SUMO runs (15 simulated minutes)."""
from __future__ import annotations

import pytest

from agents.common.sim_env import BEGIN
from agents.orchestrator import run_episode
from agents.prediction.cascade_agent import DEFAULT_MODEL

STRATS = ["S0_fixed_time", "S1_actuated", "S2_demand_gap", "S2b_max_pressure"] + (["S2F_forecast_gap"] if DEFAULT_MODEL.exists() else [])


@pytest.mark.parametrize("strategy", STRATS)
def test_no_safety_violation(tmp_path, strategy):
    k = run_episode(strategy, 5.0, 13, tmp_path / strategy, end=BEGIN + 900)
    s = k["safety"]
    assert s["transitions_checked"] > 20
    assert s["total_violations"] == 0, s["examples"]


def test_rl_agent_no_safety_violation(tmp_path):
    from agents.orchestrator import make_controller
    from app.backend.sim_manager import _default_qtable
    if not _default_qtable().exists():
        pytest.skip("Q-table not present")
    k = run_episode("S3_rl_qlearning", 5.0, 13, tmp_path / "rl", controller=make_controller("S3_rl_qlearning", qtable=_default_qtable()),
                    end=BEGIN + 900)
    assert k["safety"]["total_violations"] == 0, k["safety"]["examples"]


@pytest.mark.parametrize("strategy", ["S0_fixed_time", "S2_demand_gap"])
def test_emergency_priority_is_safe_and_acts(tmp_path, strategy):
    ev_at = BEGIN + 600
    k = run_episode(strategy, 5.0, 14, tmp_path / strategy, end=BEGIN + 1200, emergency_at=ev_at, emergency_priority=True)
    assert k["safety"]["total_violations"] == 0, k["safety"]["examples"]
    acts = k["emergency"]["actions"]
    assert k["emergency"]["travel_time_s"] is not None
    assert all(a["action"] in ("request", "serve", "release") for a in acts)


def test_monitor_detects_an_unsafe_jump(tmp_path):
    """Negative control: a green -> red jump without yellow made on purpose must be reported."""
    from agents.common.sim_env import SimEnv
    from agents.intervention.safety_monitor import SafetyMonitor
    env = SimEnv(scale=1.0, seed=1, end=BEGIN + 120)
    with env:
        mon = SafetyMonitor(env)
        tls = "-23354"
        info = env.tls[tls]
        for _ in range(40):
            env.step()
            mon.step(env.time)
        while env.api.trafficlight.getPhase(tls) not in info.green_phases:
            env.step()
            mon.step(env.time)
        g = env.api.trafficlight.getPhase(tls)
        target = next(p for p in info.green_phases if p != g)
        env.api.trafficlight.setPhase(tls, target)                 # unsafe on purpose: skips the yellow
        for _ in range(5):
            env.step()
            mon.step(env.time)
    assert mon.counts["green_to_red_without_yellow"] >= 1


def test_signals_stay_controlled_after_emergency_release(tmp_path):
    """Regression (bug found 2026-10-12): after the priority module released a signal, the actuator applied its
    3600-s hold to the yellow that had just been set, so the signal stayed yellow for the rest of the run and the
    network gridlocked. Every signal must keep receiving controller decisions after the ambulance has passed."""
    import csv
    ev_at = 26400.0
    k = run_episode("S2_demand_gap", 5.0, 2, tmp_path / "prio", end=ev_at + 900, emergency_at=ev_at, emergency_priority=True)
    ref = run_episode("S2_demand_gap", 5.0, 2, tmp_path / "ref", end=ev_at + 900, emergency_at=ev_at, emergency_priority=False)
    releases = {a["tls"]: a["time"] for a in k["emergency"]["actions"] if a["action"] == "release"}
    assert releases, "the ambulance was never served"
    with open(tmp_path / "prio" / "decisions.csv", encoding="utf-8") as fh:
        dec = list(csv.DictReader(fh, delimiter=";"))
    for tls, t_rel in releases.items():
        assert any(r["tls"] == tls and float(r["time_s"]) > t_rel + 5 for r in dec), f"{tls} never controlled again after release"
    assert k["safety"]["total_violations"] == 0, k["safety"]["examples"]
    assert k["avg_queue_veh"] < 1.5 * ref["avg_queue_veh"], (k["avg_queue_veh"], ref["avg_queue_veh"])


def test_monitor_detects_a_stuck_yellow(tmp_path):
    """Negative control (2026-10-12): a yellow kept far beyond its programmed duration must be reported while it lasts."""
    from agents.common.sim_env import SimEnv
    from agents.intervention.safety_monitor import SafetyMonitor
    env = SimEnv(scale=1.0, seed=1, end=BEGIN + 200)
    with env:
        mon = SafetyMonitor(env)
        tls = "-23354"
        info = env.tls[tls]
        for _ in range(20):
            env.step()
            mon.step(env.time)
        yellow = next(i for i, s in enumerate(info.states) if "y" in s.lower())
        env.api.trafficlight.setPhase(tls, yellow)
        env.api.trafficlight.setPhaseDuration(tls, 600)          # unsafe on purpose: yellow held 600 s
        for _ in range(30):
            env.step()
            mon.step(env.time)
    assert mon.counts["yellow_duration"] >= 1
