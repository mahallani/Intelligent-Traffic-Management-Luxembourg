"""Orchestrator: runs one SUMO episode with the 5 agents, without any human intervention.

    collection -> detection -> prediction -> decision -> intervention   (every simulation step)

Outputs of a run (all SIMULATED): SUMO tripinfo/summary, queue time series, alerts, kpis.json."""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from . import DATA_ORIGIN
from .common.sim_env import BEGIN, END, SCENARIO_DIR, WARMUP_S, SimEnv
from .decision.controllers import (DemandGapController, FixedTimeController, ForecastGapController, MaxPressureController,
                                  QLearningController)
from .detection.detection_agent import DetectionAgent
from .intervention.ambulance_tracker import AmbulanceTracker
from .intervention.emergency_priority import EmergencyPriorityAgent
from .intervention.safety_monitor import SafetyMonitor
from .intervention.tls_actuator import TLSActuator
from .kpis import run_kpis
from .observation.collection_agent import CollectionAgent
from .prediction.cascade_agent import DEFAULT_MODEL as CASCADE_MODEL, CascadePredictionAgent
from .prediction.prediction_agent import PredictionAgent

ACTUATED_FILE = SCENARIO_DIR / "additional" / "tls_actuated_v1.add.xml"
EMERGENCY_ROUTE = ["--31070#8", "--31070#7", "--31070#6", "--31070#5", "--31070#4"]   # avenue, crosses the 4 signals
STRATEGIES = ("S0_fixed_time", "S1_actuated", "S2_demand_gap", "S2F_forecast_gap", "S2b_max_pressure", "S3_rl_qlearning")


@dataclass
class Incident:
    """Simulated incident (ground truth for the detection agent): between start and end the lane's
    speed limit drops to `speed` m/s (vehicle stopped / obstruction). A full lane closure is not used
    because on these approaches it can remove the only connection to the next edge."""
    lane: str
    start: float
    end: float
    speed: float = 0.05     # ~blocked lane (vehicles crawl), connections kept


def make_controller(strategy: str, qtable: Optional[Path] = None, train: bool = False, epsilon: float = 0.0, seed: int = 0):
    if strategy in ("S0_fixed_time", "S1_actuated"):
        c = FixedTimeController()
        c.name = strategy
        return c
    if strategy == "S2_demand_gap":
        return DemandGapController()
    if strategy == "S2F_forecast_gap":
        return ForecastGapController()
    if strategy == "S2b_max_pressure":
        return MaxPressureController()
    if strategy == "S3_rl_qlearning":
        if qtable is None or (not train and not Path(qtable).exists()):
            raise FileNotFoundError("S3 needs a trained Q-table (scripts/simulation/train_rl.py)")
        return QLearningController(qtable_path=qtable, train=train, epsilon=epsilon, seed=seed)
    raise ValueError(strategy)


def run_episode(strategy: str, scale: float, seed: int, out_dir: Path, controller=None, incident: Optional[Incident] = None,
                gui: bool = False, end: float = END, label: Optional[str] = None, gui_delay_ms: float = 0.0,
                progress_every: Optional[float] = None, detection_gate: bool = False, on_step=None,
                stop_flag=None, use_forecast: bool = True, detection_mode: Optional[str] = None,
                emergency_at: Optional[float] = None, emergency_priority: bool = False) -> dict:
    """on_step(env, obs, agents) is called after each step (used by the application backend);
    stop_flag() returning True ends the episode early (clean stop, outputs are still written)."""
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not (out_dir / "kpis.json").exists():
        # a previous run was killed: keep its partial files under another name (nothing deleted)
        n = 1
        while out_dir.with_name(f"{out_dir.name}_INCOMPLETE_{n}").exists():
            n += 1
        out_dir.rename(out_dir.with_name(f"{out_dir.name}_INCOMPLETE_{n}"))
    out_dir.mkdir(parents=True, exist_ok=True)
    controller = controller or make_controller(strategy)
    additional = [ACTUATED_FILE] if strategy == "S1_actuated" else []
    env = SimEnv(scale=scale, seed=seed, out_dir=out_dir, gui=gui, additional_files=additional,
                 label=label or f"{strategy}_{scale}_{seed}_{time.time_ns()}", end=end, gui_delay_ms=gui_delay_ms)
    t0 = time.time()
    try:
        env.start()                      # inside try (2026-10-15): SUMO is closed whatever happens next
        programs = {t: env.api.trafficlight.getProgram(t) for t in env.tls}
        if strategy == "S1_actuated" and set(programs.values()) != {"actuated_v1"}:
            raise RuntimeError(f"actuated programs not active: {programs}")
        col = CollectionAgent(env)
        mode = detection_mode or ("gated" if detection_gate else "rules")
        det = DetectionAgent(env, gate_with_forecast=(mode == "gated"), discharge_rule=(mode == "discharge"))
        pred = CascadePredictionAgent(env, col) if CASCADE_MODEL.exists() else PredictionAgent(env)
        if strategy == "S2F_forecast_gap" and not isinstance(pred, CascadePredictionAgent):
            raise FileNotFoundError(f"S2F needs the cascade model {CASCADE_MODEL}")
        act = TLSActuator(env, enabled=controller.adaptive)
        safety = SafetyMonitor(env)
        emerg = EmergencyPriorityAgent(env, actuator=act) if emergency_priority else None
        # observation + drawing only (colour, sumo-gui camera/beacon): no effect on dynamics (2026-10-22)
        amb = AmbulanceTracker(env, gui=gui, priority_agent=emerg) if emergency_at is not None else None
        tls_lanes = {t: i.in_lanes for t, i in env.tls.items()}
        inc_log = {}
        stopped_early, obs = False, None
        while not env.done():
            if stop_flag is not None and stop_flag():
                stopped_early = True
                break
            env.step()
            obs = col.observe()
            if emergency_at is not None and obs.time == emergency_at:
                env.api.route.add("ev_route", EMERGENCY_ROUTE)
                env.api.vehicle.add("ambulance", "ev_route", typeID="emergency_plain", departLane="best", departSpeed="max")
                amb.inserted(obs.time)
            if emerg is not None:
                emerg.step(obs)
            if amb is not None:
                amb.step(obs)
            if incident:
                if obs.time == incident.start:
                    inc_log["original_speed"] = env.api.lane.getMaxSpeed(incident.lane)
                    env.api.lane.setMaxSpeed(incident.lane, incident.speed)
                    inc_log["applied_at"] = obs.time
                elif obs.time == incident.end:
                    env.api.lane.setMaxSpeed(incident.lane, inc_log["original_speed"])
                    inc_log["removed_at"] = obs.time
            if isinstance(pred, CascadePredictionAgent):
                forecasts = pred.update(obs)
            else:
                pred.update(obs, tls_lanes)
                forecasts = None
            det.update(obs, predictor=pred if isinstance(pred, CascadePredictionAgent) else None)
            acts = controller.decide(obs, env, forecasts=forecasts if use_forecast else None)
            act.step(obs, acts, explain=getattr(controller, "last_explain", None))
            safety.step(obs.time)
            if on_step is not None:
                on_step(env, obs, {"collection": col, "detection": det, "prediction": pred, "actuator": act,
                                   "controller": controller, "forecasts": forecasts, "ambulance": amb})
            if progress_every and obs.fresh and int(obs.time - BEGIN) % int(progress_every) == 0:
                last = col.samples[-1]
                print(f"[{strategy}] t={int(obs.time - BEGIN):5d}s  vehicles={last['vehicles_in_network']:4d}  "
                      f"halted={last['halting_total']:4d}  phases={obs.phase}  phase changes by agent={act.stats['advance']}"
                      f"  alerts={len(det.alerts)}", flush=True)
        if amb is not None:
            amb.finish(obs.time if obs is not None else 0.0)
        controller.end_episode(obs, env)
    finally:
        env.close()
    meta = {"strategy": strategy, "scale": scale, "seed": seed, "begin": BEGIN, "end": end,
            "backend": env.conn.backend, "stopped_early": stopped_early, "forecasts_passed_to_decision": use_forecast,
            "warmup_s": WARMUP_S, "programs_at_start": programs, "wall_clock_s": round(time.time() - t0, 1)}
    k = run_kpis(out_dir, col.samples, BEGIN + WARMUP_S, meta)
    k["actuator"] = act.stats
    k["safety"] = safety.summary()
    if emergency_at is not None:
        import xml.etree.ElementTree as _ET
        ev = next((e for e in _ET.parse(out_dir / "tripinfo.xml").getroot().iter("tripinfo") if e.get("id") == "ambulance"), None)
        k["emergency"] = {"inserted_at": emergency_at, "priority": emergency_priority, "route": EMERGENCY_ROUTE,
                          "travel_time_s": float(ev.get("duration")) if ev is not None and float(ev.get("arrival", -1)) > 0 else None,
                          "waiting_time_s": float(ev.get("waitingTime")) if ev is not None else None,
                          "actions": emerg.log if emerg is not None else []}
    k["controller"] = getattr(controller, "stats", {})
    k["detection"] = {"mode": mode, "gate_with_forecast": det.gate, "suppressed_by_forecast": det.suppressed, "alerts": len(det.alerts), "alerts_congestion": sum(a.rule == "congestion" for a in det.alerts),
                      "alerts_stalled": sum(a.rule == "stalled" for a in det.alerts),
                      "rules": f"congestion: halting >= {det.min_halting} for >= {det.min_duration:.0f} s; "
                               f"stalled: a vehicle stopped >= {det.stall_s:.0f} s"}
    k["prediction"] = pred.scores()
    if incident:
        hits = [a for a in det.alerts if a.lane.rsplit("_", 1)[0] == incident.lane.rsplit("_", 1)[0]
                and incident.start <= a.raised <= incident.end + det.min_duration]
        k["incident"] = {**asdict(incident), **inc_log,
                         "detected": bool(hits), "detection_delay_s": (hits[0].raised - incident.start) if hits else None}
    with open(out_dir / "queue_timeseries.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        tls_ids = list(env.tls)
        w.writerow(["time_s", "halting_total", "queue_m_total", "vehicles_in_network"] + [f"halting_{t}" for t in tls_ids] + ["data_origin"])
        for s in col.samples:
            w.writerow([s["time"], s["halting_total"], s["queue_m_total"], s["vehicles_in_network"]] +
                       [s["halting_by_tls"][t] for t in tls_ids] + [DATA_ORIGIN])
    if amb is not None:      # ambulance timeline (2026-10-22): observation + priority-module log, nothing else
        with open(out_dir / "ambulance_events.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["time_s", "clock", "event", "tls", "carrefour", "detail", "data_origin"])
            for e in amb.events:
                w.writerow([e["time_s"], e["clock"], e["event"], e["tls"], e["carrefour"], e["detail"], DATA_ORIGIN])
    with open(out_dir / "alerts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["lane", "tls", "rule", "start_s", "raised_s", "end_s", "max_halting", "data_origin"])
        for a in det.alerts:
            w.writerow([a.lane, a.tls, a.rule, a.start, a.raised, a.end, a.max_halting, DATA_ORIGIN])
    if isinstance(pred, CascadePredictionAgent) and pred.log:
        with open(out_dir / "predictions.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(pred.log[0]) + ["data_origin"], delimiter=";")
            w.writeheader()
            w.writerows({**r, "data_origin": DATA_ORIGIN} for r in pred.log)
    with open(out_dir / "decisions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["time_s", "tls", "from_phase", "to_phase", "green_duration_s", "reason", "controller", "data_origin", "explanation"])
        for row in act.log:
            ex = row[6] if len(row) > 6 else None
            w.writerow(list(row[:6]) + [strategy, DATA_ORIGIN, json.dumps(ex, ensure_ascii=False) if ex else ""])
    (out_dir / "kpis.json").write_text(json.dumps(k, indent=1), encoding="utf-8")
    return k
