"""Tests of the multi-agent layer (agents/) on the Kirchberg 4-signal scenario.
Short SUMO runs (10 min of simulated time). Run: python -m pytest tests/test_agents.py -v"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import DATA_ORIGIN
from agents.common.sim_env import BEGIN, TLS_IDS, SimEnv
from agents.decision.controllers import (ADVANCE, KEEP, DemandGapController, QLearningController)
from agents.detection.detection_agent import DetectionAgent
from agents.intervention.tls_actuator import TLSActuator
from agents.kpis import trip_kpis
from agents.observation.collection_agent import CollectionAgent, Observation
from agents.orchestrator import ACTUATED_FILE, run_episode
from agents.prediction.prediction_agent import PredictionAgent

QTABLE = Path(__file__).resolve().parents[1] / "sumo/lust_4_intersections/output/experiments_v1/rl/qtable_v4_FROZEN_ep26_eval.json"
SHORT = BEGIN + 600


class FakeEnv:
    def __init__(self, tls):
        self.tls = tls


def test_topology_of_the_four_signals():
    env = SimEnv(scale=1.0, seed=1, end=BEGIN + 1)
    with env:
        assert sorted(env.tls) == sorted(TLS_IDS)
        for info in env.tls.values():
            assert info.green_phases and all(info.is_green(info.states[p]) for p in info.green_phases)
            for p, links in info.phase_links.items():
                assert links and all(i in info.in_lanes and o in info.out_lanes for i, o in links)


def test_actuator_keeps_order_yellow_min_and_max_green():
    env = SimEnv(scale=5.0, seed=7, end=SHORT)
    with env:
        col, ctrl, act = CollectionAgent(env), DemandGapController(), TLSActuator(env)
        seq = {t: [] for t in env.tls}
        while not env.done():
            env.step()
            obs = col.observe()
            act.step(obs, ctrl.decide(obs, env))
            for t in env.tls:
                if not seq[t] or seq[t][-1][0] != obs.phase[t]:
                    seq[t].append((obs.phase[t], obs.time))
        assert act.stats["advance"] > 10
        for t, s in seq.items():
            info = env.tls[t]
            for (p, t0), (q, t1) in zip(s[1:], s[2:]):         # skip the first (partial) phase
                assert q == (p + 1) % len(info.states), (t, p, q)  # LuST phase order kept
                dur = t1 - t0
                if p in info.green_phases:
                    assert 5 <= dur <= min(60, 2 * info.durations[p]) + 1, (t, p, dur)
                else:
                    assert dur == pytest.approx(info.durations[p], abs=1), (t, p, dur)  # yellow kept


def test_actuated_programs_are_loaded_for_S1(tmp_path):
    assert ACTUATED_FILE.exists()
    k = run_episode("S1_actuated", 1.0, 1, tmp_path / "s1", end=BEGIN + 120)
    assert set(k["programs_at_start"].values()) == {"actuated_v1"}
    assert k["data_origin"] == DATA_ORIGIN


@pytest.mark.skipif(not QTABLE.exists(), reason="trained Q-table not present")
def test_rl_agent_decides_alone_in_sumo(tmp_path):
    ctrl = QLearningController(qtable_path=QTABLE, train=False)
    k = run_episode("S3_rl_qlearning", 5.0, 9, tmp_path / "rl", controller=ctrl, end=SHORT)
    assert ctrl.stats["decisions"] > 50 and ctrl.stats["explorations"] == 0 and ctrl.stats["updates"] == 0
    assert k["actuator"]["advance"] > 0
    saved = json.loads((tmp_path / "rl" / "kpis.json").read_text())
    assert saved["strategy"] == "S3_rl_qlearning" and saved["data_origin"] == DATA_ORIGIN


def test_rl_training_updates_and_saves(tmp_path):
    q = tmp_path / "q.json"
    ctrl = QLearningController(qtable_path=q, train=True, epsilon=0.2, seed=1)
    run_episode("S3_rl_qlearning", 1.0, 11, tmp_path / "train", controller=ctrl, end=SHORT)
    assert ctrl.stats["updates"] > 0 and ctrl.q
    ctrl.save(q, 11, 1.0)
    again = QLearningController(qtable_path=q)
    assert again.meta["episodes_trained"] == 1 and again.q == ctrl.q


def test_detection_rules():
    lanes = {"L_0": None}
    det = DetectionAgent.__new__(DetectionAgent)
    det.__init__(FakeEnv({"T": type("I", (), {"in_lanes": ["L_0"]})()}))
    def obs(t, h, w=0.0):
        return Observation(t, {}, {}, {"L_0": (h, h, 0.0)}, True, {"L_0": w})
    assert det.update(obs(0, 9)) == []                      # congestion must last 60 s
    assert det.update(obs(55, 9)) == []
    a = det.update(obs(60, 9))
    assert len(a) == 1 and a[0].rule == "congestion" and a[0].start == 0
    det.update(obs(65, 0))
    assert det.alerts[0].end == 65
    b = det.update(obs(70, 1, w=151))                       # one vehicle stopped > 150 s
    assert len(b) == 1 and b[0].rule == "stalled"
    assert lanes


def test_prediction_scores_against_persistence():
    pred = PredictionAgent(FakeEnv({"T": None}), horizon_s=10, window_s=20)
    for i, t in enumerate(range(0, 60, 5)):
        pred.update(Observation(float(t), {}, {}, {"L": (2 * i, 2 * i, 0.0)}, True), {"T": ["L"]})
    s = pred.scores()
    assert s["n_scored"] > 0 and s["mae_model_veh"] < s["mae_persistence_veh"]   # linear trend beats persistence


def test_kpis_from_tripinfo(tmp_path):
    f = tmp_path / "tripinfo.xml"
    f.write_text('<tripinfos><tripinfo id="a" duration="100" waitingTime="10" timeLoss="20" departDelay="1" routeLength="900" arrival="200">'
                 '<emissions CO2_abs="2000000" NOx_abs="1000" PMx_abs="10" fuel_abs="600000"/></tripinfo>'
                 '<tripinfo id="b" duration="50" waitingTime="30" timeLoss="40" departDelay="0" routeLength="100" arrival="-1">'
                 '<emissions CO2_abs="1000000" NOx_abs="0" PMx_abs="0" fuel_abs="0"/></tripinfo></tripinfos>')
    k = trip_kpis(f)
    assert k["completed_trips"] == 1 and k["unfinished_trips_at_end"] == 1
    assert k["avg_travel_time_s"] == 100 and k["co2_kg"] == 3.0 and k["total_waiting_time_all_h"] == pytest.approx(40 / 3600, abs=0.01)


def test_demand_gap_rule():
    ctrl = DemandGapController()
    info = type("I", (), {"green_phases": [0, 2], "phase_links": {0: [("a", "x")], 2: [("b", "y")]}})()
    o = Observation(0, {"T": 0}, {"T": 20}, {"a": (0, 1, 0), "b": (3, 3, 0)}, True)
    assert ctrl.rule(o, info, "T") == ADVANCE
    o = Observation(0, {"T": 0}, {"T": 20}, {"a": (4, 6, 0), "b": (3, 3, 0)}, True)
    assert ctrl.rule(o, info, "T") == KEEP


def test_real_data_guard_blocks_untrainable_objectives():
    from agents.common.real_data import READINESS, NotEnoughRealData, require_trainable
    if not READINESS.exists():
        pytest.skip("readiness report not built")
    for obj in ("A", "B"):
        with pytest.raises(NotEnoughRealData):
            require_trainable(obj)
