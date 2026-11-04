"""One simulation at a time, run in a worker thread through agents.orchestrator.run_episode.

States: idle -> starting -> running <-> paused -> (stopping) -> finished | stopped | error.
A second start while a simulation is active is refused (no concurrent SUMO / TraCI). Pause blocks the
simulation loop between two steps; stop makes run_episode leave its loop cleanly, so SUMO is closed and
the outputs of the partial run (tripinfo, kpis.json, CSVs) are still written."""
from __future__ import annotations

import copy
import threading
import time
from datetime import datetime
from pathlib import Path

from agents import DATA_ORIGIN
from agents.common.sim_env import BEGIN, END, SCENARIO_DIR
from agents.orchestrator import STRATEGIES, make_controller, run_episode

OUTPUT = SCENARIO_DIR / "output"
APP_RUNS = OUTPUT / "app_runs"
SCENARIOS = {"kirchberg_4tls": "Kirchberg – avenue J.F. Kennedy, 4 feux (LuST 07:00–08:00)"}
DETECTION_MODES = ("discharge", "rules", "gated")
# Simulated incidents offered by the application (2026-10-22): the two lanes used in the detection evaluation
# (experiments_v1/detection_v2), lane speed limit 0.05 m/s from 07:20 to 07:40. SIMULATED ground truth.
INCIDENTS = {"none": None,
             "carrefour4": {"lane": "-31070#4_1", "tls": "-29958", "label": "Voie bloquée à l'approche du Carrefour 4 (07:20-07:40)"},
             "carrefour1": {"lane": "--31070#8_1", "tls": "-28692", "label": "Voie bloquée à l'approche du Carrefour 1 (07:20-07:40)"}}
INCIDENT_START, INCIDENT_END, AMBULANCE_AT = 26400.0, 27600.0, 26400.0


class Busy(RuntimeError):
    pass


def clock(t: float) -> str:
    s = int(t)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class SimulationManager:
    def __init__(self, runs_dir: Path = APP_RUNS):
        self.runs_dir = Path(runs_dir)
        self._lock = threading.Lock()
        self._pause = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = {"status": "idle"}
        self._tracker: dict = {}
        # XAI (2026-10-29): the COMPLETE decision log of the current run (the state only keeps the last 40) and its
        # folder, so /api/xai/* can list and explain every real decision while the run is active and after it ends.
        self._decision_log: list = []
        self._run_dir: Path | None = None

    # ------------------------------------------------------------------ public API
    def state(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self, scenario: str = "kirchberg_4tls", strategy: str = "S0_fixed_time", scale: float = 1.0, seed: int = 1,
              delay_ms: float = 0.0, gui: bool = False, use_forecast: bool = True, detection_mode: str = "discharge",
              end: float = END, qtable: Path | None = None, incident: str = "none", ambulance: bool = False,
              ambulance_priority: bool = True) -> dict:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy}")
        if detection_mode not in DETECTION_MODES:
            raise ValueError(f"unknown detection mode {detection_mode}")
        if not (0.1 <= float(scale) <= 10):
            raise ValueError("scale must be between 0.1 and 10")
        if incident not in INCIDENTS:
            raise ValueError(f"unknown incident {incident}")
        if gui:   # sumo-gui unusable (e.g. missing DLL): clear refusal, no empty run folder (2026-10-15)
            from agents.common.sim_env import sumo_binary_status
            ok, msg = sumo_binary_status(True)
            if not ok:
                raise ValueError(msg + ". Décoche SUMO-GUI pour lancer la simulation sans fenêtre SUMO.")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise Busy(f"a simulation is already {self._state.get('status')}: stop it first")
            controller = make_controller(strategy, qtable=qtable) if qtable else \
                make_controller(strategy, **({"qtable": _default_qtable()} if strategy == "S3_rl_qlearning" else {}))
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = self.runs_dir / (f"{stamp}_{strategy}_x{float(scale):g}_seed{int(seed)}" + (f"_incident_{incident}" if INCIDENTS[incident] else "")
                                   + (("_ambulance_prio" if ambulance_priority else "_ambulance") if ambulance else ""))
            self._pause.clear()
            self._stop.clear()
            self._decision_log, self._run_dir = [], out
            self._tracker = {"depart": {}, "travel": [], "halted_veh_s": 0.0, "co2_mg": 0.0, "last_fresh": None,
                             "halted_tls_s": {}}      # 2026-11-03: stop time per signal (veh x s), for the Carrefours page
            self._state = {"status": "starting", "scenario": scenario, "strategy": strategy, "scale": float(scale), "seed": int(seed),
                           "delay_ms": float(delay_ms), "gui": bool(gui), "use_forecast": bool(use_forecast),
                           "detection_mode": detection_mode, "run_dir": _display_path(out),
                           "incident": ({"id": incident, **INCIDENTS[incident], "start": clock(INCIDENT_START), "end": clock(INCIDENT_END)}
                                        if INCIDENTS[incident] else None),
                           "ambulance": ({"at": clock(AMBULANCE_AT), "priority": bool(ambulance_priority)} if ambulance else None),
                           "prediction_checks": [], "emergency_live": None,
                           "run_id": f"{self.runs_dir.name}/{out.name}", "started_at": datetime.now().isoformat(timespec="seconds"),
                           "sim_time": BEGIN, "clock": clock(BEGIN), "progress": 0.0, "signals": {}, "vehicles": [],
                           "decisions": [], "alerts": [], "forecasts": {}, "live": {},
                           "series": {"t": [], "halting": [], "vehicles": [], "speed": [],
                                      # 2026-11-03 (additive): waiting, CO2 and stopped vehicles per signal over time
                                      "waiting": [], "co2": [], "halting_by_tls": {}}, "error": None,
                           "final_kpis": None, "data_origin": DATA_ORIGIN}
            args = dict(strategy=strategy, scale=float(scale), seed=int(seed), out_dir=out, controller=controller, gui=bool(gui),
                        end=end, gui_delay_ms=float(delay_ms) if gui else 0.0, use_forecast=bool(use_forecast),
                        detection_mode=detection_mode)
            if INCIDENTS[incident]:
                from agents.orchestrator import Incident
                args["incident"] = Incident(INCIDENTS[incident]["lane"], INCIDENT_START, INCIDENT_END)
            if ambulance:
                args["emergency_at"] = AMBULANCE_AT
                args["emergency_priority"] = bool(ambulance_priority)
            self._thread = threading.Thread(target=self._run, args=(args, float(delay_ms) if not gui else 0.0), daemon=True)
            self._thread.start()
            return copy.deepcopy(self._state)

    def pause(self) -> dict:
        with self._lock:
            if self._state.get("status") != "running":
                raise Busy("no running simulation to pause")
            self._pause.set()
            self._state["status"] = "paused"
            return copy.deepcopy(self._state)

    def resume(self) -> dict:
        with self._lock:
            if self._state.get("status") != "paused":
                raise Busy("the simulation is not paused")
            self._pause.clear()
            self._state["status"] = "running"
            return copy.deepcopy(self._state)

    def stop(self, wait_s: float = 30.0) -> dict:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                raise Busy("no active simulation")
            self._state["status"] = "stopping"
            self._stop.set()
            self._pause.clear()
        self._thread.join(timeout=wait_s)
        return self.state()

    def decision_snapshot(self) -> dict:
        """XAI (2026-10-29): status, strategy, run folder and a copy of the full decision log of the current run.
        Log rows = TLSActuator.log: (time_s, tls, from_phase, to_phase, green_s, reason, explanation)."""
        with self._lock:
            return {"status": self._state.get("status"), "strategy": self._state.get("strategy"),
                    "run_id": self._state.get("run_id"), "run_dir": self._run_dir,
                    "active": self._thread is not None and self._thread.is_alive(),
                    "log": list(self._decision_log)}

    def wait(self, timeout: float | None = None) -> dict:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.state()

    # ------------------------------------------------------------------ worker
    def _run(self, args: dict, delay_ms: float):
        try:
            with self._lock:
                self._state["status"] = "running"
            k = run_episode(on_step=lambda env, obs, ag: self._on_step(env, obs, ag, delay_ms), stop_flag=self._stop.is_set, **args)
            with self._lock:
                self._state["final_kpis"] = {x: v for x, v in k.items() if not isinstance(v, (dict, list))}
                for key in ("safety", "prediction", "detection", "emergency", "incident"):   # nested summaries shown in the UI
                    if isinstance(k.get(key), dict):
                        self._state["final_kpis"][key] = k[key]
                self._state["status"] = "stopped" if k.get("stopped_early") else "finished"
        except Exception as exc:  # reported to the user, never silent
            self._report_error(exc, args.get("out_dir"))

    def _report_error(self, exc: Exception, out_dir) -> None:
        """Error shown by the interface AND written next to the run (app_error.json), with SUMO's own messages
        when SUMO could not start (2026-10-15)."""
        import json
        import traceback
        detail = {"time": datetime.now().isoformat(timespec="seconds"), "error_type": type(exc).__name__,
                  "error": str(exc), "traceback": traceback.format_exc()}
        if hasattr(exc, "as_dict"):
            detail.update(exc.as_dict())
        if out_dir is not None:
            try:
                Path(out_dir).mkdir(parents=True, exist_ok=True)
                with open(Path(out_dir) / "app_error.json", "x", encoding="utf-8") as fh:   # never overwrite
                    json.dump(detail, fh, ensure_ascii=False, indent=1)
                detail["error_file"] = str(Path(out_dir) / "app_error.json")
            except OSError:
                pass
        with self._lock:
            self._state["status"] = "error"
            self._state["error"] = f"{type(exc).__name__}: {exc}"
            self._state["error_detail"] = {k: detail.get(k) for k in ("returncode", "returncode_meaning", "launches",
                                                                       "sumo_output_tail", "process_log", "error_file")}

    def shutdown(self, wait_s: float = 30.0) -> None:
        """Called when the backend stops (Ctrl+C): the active simulation is stopped cleanly, so SUMO is closed and
        the partial outputs (kpis.json with stopped_early = true) are written instead of a killed run."""
        if self._thread is not None and self._thread.is_alive():
            try:
                self.stop(wait_s=wait_s)
            except Busy:
                pass

    def _on_step(self, env, obs, ag, delay_ms: float):
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.1)
        api, t = env.api, obs.time
        if self._decision_log is not ag["actuator"].log:     # XAI: keep a reference to the full log (2026-10-29)
            with self._lock:
                self._decision_log = ag["actuator"].log
        amb = ag.get("ambulance")
        if amb is not None:      # ambulance tracking, every step (observation only; 2026-10-22)
            with self._lock:
                self._state["emergency_live"] = amb.as_state()
        tr = self._tracker
        for v in api.simulation.getDepartedIDList():
            tr["depart"][v] = t
        for v in api.simulation.getArrivedIDList():
            if v in tr["depart"]:
                tr["travel"].append(t - tr["depart"].pop(v))
        if obs.fresh:
            ids = api.vehicle.getIDList()
            speeds, pos, halted, co2 = [], [], 0, 0.0
            for v in ids:
                sp = api.vehicle.getSpeed(v)
                x, y = api.vehicle.getPosition(v)
                speeds.append(sp)
                pos.append([round(x, 1), round(y, 1), 1 if sp < 0.1 else 0])
                halted += sp < 0.1
                co2 += api.vehicle.getCO2Emission(v)
            dt = 5.0 if tr["last_fresh"] is None else t - tr["last_fresh"]
            tr["last_fresh"] = t
            tr["halted_veh_s"] += halted * dt
            tr["co2_mg"] += co2 * dt
            for tid, n in ag["collection"].samples[-1]["halting_by_tls"].items():     # 2026-11-03: stop time per signal
                tr["halted_tls_s"][tid] = tr["halted_tls_s"].get(tid, 0.0) + n * dt
            sample = ag["collection"].samples[-1]
            departed = len(tr["depart"]) + len(tr["travel"])
            act, det, pred = ag["actuator"], ag["detection"], ag["prediction"]
            signals = {tid: {"phase": obs.phase[tid], "state": api.trafficlight.getRedYellowGreenState(tid),
                             "green_elapsed": obs.green_elapsed[tid], "halting": sample["halting_by_tls"][tid]} for tid in env.tls}
            live = {"vehicles": len(ids), "halting": sample["halting_total"],
                    "mean_speed_kmh": round(3.6 * sum(speeds) / len(speeds), 1) if speeds else None,
                    "arrived": len(tr["travel"]),
                    "avg_travel_time_s": round(sum(tr["travel"]) / len(tr["travel"]), 1) if tr["travel"] else None,
                    "avg_waiting_s": round(tr["halted_veh_s"] / departed, 1) if departed else None,
                    "co2_kg": round(tr["co2_mg"] / 1e6, 1),
                    "stop_min_by_tls": {tid: round(v / 60.0, 1) for tid, v in tr["halted_tls_s"].items()},   # 2026-11-03
                    "note": "live approximations; exact KPIs from SUMO tripinfo at the end of the run"}
            forecasts = {}
            if ag.get("forecasts"):
                forecasts = {tid: {"now": round(f["now"], 2), **{str(h): round(f[h], 2) for h in (300, 600, 900)}}
                             for tid, f in ag["forecasts"].items()}
            with self._lock:
                st = self._state
                st.update(sim_time=t, clock=clock(t), progress=min(1.0, (t - BEGIN) / (END - BEGIN)), signals=signals,
                          vehicles=pos[:2000], live=live)
                if forecasts:
                    st["forecasts"] = forecasts
                if hasattr(pred, "scores"):
                    sc = pred.scores()
                    if sc.get("n_scored"):
                        st["prediction_scores"] = sc
                s = st["series"]
                s["t"].append(t)
                s["halting"].append(sample["halting_total"])
                s["vehicles"].append(len(ids))
                s["speed"].append(live["mean_speed_kmh"] or 0)
                s.setdefault("waiting", []).append(live["avg_waiting_s"] or 0)          # 2026-11-03 (additive)
                s.setdefault("co2", []).append(live["co2_kg"])
                for tid, n in sample["halting_by_tls"].items():
                    s.setdefault("halting_by_tls", {}).setdefault(tid, []).append(n)
                st["decisions"] = [{"clock": clock(r[0]), "tls": r[1], "from_phase": r[2], "to_phase": r[3],
                                    "green_duration_s": r[4], "reason": r[5], "explain": r[6] if len(r) > 6 else None}
                                   for r in act.log[-40:]][::-1]
                if hasattr(pred, "log"):    # forecasts whose target time is reached: forecast vs observed (2026-10-22)
                    st["prediction_checks"] = [{"made": clock(r["origin_s"]), "target": clock(r["target_s"]), "tls": r["tls"],
                                                "horizon_min": r["horizon_min"], "forecast": round(r["forecast"], 2),
                                                "observed": round(r["observed"], 2), "error": round(r["error"], 2),
                                                "persistence": round(r["persistence"], 2)} for r in pred.log[-24:]][::-1]
                st["alerts"] = [{"clock": clock(a.raised), "lane": a.lane, "tls": a.tls, "rule": a.rule, "max_halting": a.max_halting,
                                 "end_clock": clock(a.end) if a.end else None} for a in det.alerts[-40:]][::-1]
        if delay_ms:
            time.sleep(delay_ms / 1000.0)


def _display_path(p: Path) -> str:
    """Path shown in the UI: relative to the project root when possible, absolute otherwise (tests use tmp dirs)."""
    root = OUTPUT.parent.parent.parent
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p)


def _default_qtable() -> Path:
    return OUTPUT / "experiments_v1" / "rl" / "qtable_v4_FROZEN_ep26_eval.json"
