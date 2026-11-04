# applied from the project root on the device; backups made before (bak_20261012c)
import shutil
from pathlib import Path
for f in ("agents/orchestrator.py", "agents/intervention/tls_actuator.py", "scripts/simulation/run_experiment.py"):
    b = Path(f + ".bak_20261012c")
    if not b.exists():
        shutil.copy2(f, b)

p = Path("agents/intervention/tls_actuator.py"); s = p.read_text()
if "self.locked" not in s:
    s = s.replace('''        self.log: list[tuple] = []   # (time, tls, from_phase, to_phase, green_s, reason)''',
                  '''        self.log: list[tuple] = []   # (time, tls, from_phase, to_phase, green_s, reason)
        self.locked: set[str] = set()  # signals temporarily under emergency-priority control''')
    s = s.replace('''        for tid, info in self.env.tls.items():
            p = obs.phase[tid]
            if p not in info.green_phases:''', '''        for tid, info in self.env.tls.items():
            if tid in self.locked:                          # emergency priority has the signal
                self.held.pop(tid, None)
                continue
            p = obs.phase[tid]
            if p not in info.green_phases:''')
    assert "self.locked" in s and "if tid in self.locked" in s
    p.write_text(s)

p = Path("agents/orchestrator.py"); s = p.read_text()
if "SafetyMonitor" not in s:
    s = s.replace('''from .intervention.tls_actuator import TLSActuator''', '''from .intervention.emergency_priority import EmergencyPriorityAgent
from .intervention.safety_monitor import SafetyMonitor
from .intervention.tls_actuator import TLSActuator''')
    s = s.replace('''ACTUATED_FILE = SCENARIO_DIR / "additional" / "tls_actuated_v1.add.xml"''', '''ACTUATED_FILE = SCENARIO_DIR / "additional" / "tls_actuated_v1.add.xml"
EMERGENCY_ROUTE = ["--31070#8", "--31070#7", "--31070#6", "--31070#5", "--31070#4"]   # avenue, crosses the 4 signals''')
    s = s.replace('''                stop_flag=None, use_forecast: bool = True, detection_mode: Optional[str] = None) -> dict:''',
                  '''                stop_flag=None, use_forecast: bool = True, detection_mode: Optional[str] = None,
                emergency_at: Optional[float] = None, emergency_priority: bool = False) -> dict:''')
    s = s.replace('''        act = TLSActuator(env, enabled=controller.adaptive)''', '''        act = TLSActuator(env, enabled=controller.adaptive)
        safety = SafetyMonitor(env)
        emerg = EmergencyPriorityAgent(env, actuator=act) if emergency_priority else None''')
    s = s.replace('''            env.step()
            obs = col.observe()''', '''            env.step()
            obs = col.observe()
            if emergency_at is not None and obs.time == emergency_at:
                env.api.route.add("ev_route", EMERGENCY_ROUTE)
                env.api.vehicle.add("ambulance", "ev_route", typeID="emergency_plain", departLane="best", departSpeed="max")
            if emerg is not None:
                emerg.step(obs)''')
    s = s.replace('''            act.step(obs, controller.decide(obs, env, forecasts=forecasts if use_forecast else None))''',
                  '''            act.step(obs, controller.decide(obs, env, forecasts=forecasts if use_forecast else None))
            safety.step(obs.time)''')
    s = s.replace('''    k["actuator"] = act.stats''', '''    k["actuator"] = act.stats
    k["safety"] = safety.summary()
    if emergency_at is not None:
        import xml.etree.ElementTree as _ET
        ev = next((e for e in _ET.parse(out_dir / "tripinfo.xml").getroot().iter("tripinfo") if e.get("id") == "ambulance"), None)
        k["emergency"] = {"inserted_at": emergency_at, "priority": emergency_priority, "route": EMERGENCY_ROUTE,
                          "travel_time_s": float(ev.get("duration")) if ev is not None and float(ev.get("arrival", -1)) > 0 else None,
                          "waiting_time_s": float(ev.get("waitingTime")) if ev is not None else None,
                          "actions": emerg.log if emerg is not None else []}''')
    assert "safety.step(obs.time)" in s and "EmergencyPriorityAgent(env" in s and 'k["safety"]' in s
    p.write_text(s)

p = Path("scripts/simulation/run_experiment.py"); s = p.read_text()
if "--emergency-at" not in s:
    s = s.replace('''    p.add_argument("--no-forecast", action="store_true", help="do not pass the cascade forecasts to the decision agent")''',
                  '''    p.add_argument("--no-forecast", action="store_true", help="do not pass the cascade forecasts to the decision agent")
    p.add_argument("--emergency-at", type=float, default=None, help="insert an ambulance on the avenue at this time (s)")
    p.add_argument("--emergency-priority", action="store_true", help="enable the emergency-priority module")''')
    s = s.replace('''            ("_noforecast" if a.no_forecast else "")''', '''            ("_noforecast" if a.no_forecast else "") + \\
            (f"_ev{int(a.emergency_at)}{'_prio' if a.emergency_priority else ''}" if a.emergency_at else "")''')
    s = s.replace('''                        use_forecast=not a.no_forecast, detection_gate=a.detection_gate)''',
                  '''                        use_forecast=not a.no_forecast, detection_gate=a.detection_gate,
                        emergency_at=a.emergency_at, emergency_priority=a.emergency_priority)''')
    assert "emergency_priority=a.emergency_priority" in s
    p.write_text(s)
print("patch p1 applied")
