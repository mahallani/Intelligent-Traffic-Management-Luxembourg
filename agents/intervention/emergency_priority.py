"""Simulated priority for emergency vehicles - an INTERVENTION MODULE, separate from the signal controllers
(S0/S1/S2/S3). It works on top of any strategy and is evaluated on its own (scripts/simulation/evaluate_emergency.py).

When an emergency vehicle (vClass emergency) is within `detect_m` of one of the 4 signals and its movement is red:
  1. if the current phase is green, it is ended only after `min_green` seconds and ALWAYS through its
     programmed yellow (no green -> red jump);
  2. after the yellow, the first green phase of the program that serves the vehicle's movement is set;
  3. that green is held while the vehicle approaches (at most `max_hold_s`), then the program continues with
     the yellow that follows it.
While a signal is under emergency control, the adaptive controller of that signal is suspended
(TLSActuator.locked). This is a simulation feature: it never commands physical signals."""
from __future__ import annotations


class EmergencyPriorityAgent:
    name = "emergency_priority"

    def __init__(self, env, actuator=None, detect_m: float = 150.0, max_hold_s: float = 30.0, min_green: float = 5.0):
        self.env, self.actuator = env, actuator
        self.detect_m, self.max_hold, self.min_green = detect_m, max_hold_s, min_green
        self.mode: dict[str, dict] = {}       # tls -> {"stage": "clearing"|"serving", "target": p, "since": t, "veh": id}
        self.log: list[dict] = []

    def _target_phase(self, info, link_index):
        for p in info.green_phases:
            if info.states[p][link_index] == "G":
                return p
        for p in info.green_phases:
            if info.states[p][link_index] == "g":
                return p
        return None

    def step(self, obs):
        api, t = self.env.api, obs.time
        evs = [v for v in api.vehicle.getIDList() if api.vehicle.getVehicleClass(v) == "emergency"]
        wanted = {}
        for v in evs:
            for (tls, link, dist, state) in api.vehicle.getNextTLS(v)[:1]:
                if tls in self.env.tls and dist <= self.detect_m:
                    wanted[tls] = (v, link, state)
        for tls, info in self.env.tls.items():
            m = self.mode.get(tls)
            p = obs.phase[tls]
            if m is None:
                if tls not in wanted or wanted[tls][2] in "Gg":
                    continue
                v, link, _ = wanted[tls]
                target = self._target_phase(info, link)
                if target is None:
                    continue
                if p in info.green_phases and obs.green_elapsed[tls] < self.min_green:
                    continue                                  # wait for the minimum green
                self.mode[tls] = {"stage": "clearing", "target": target, "since": t, "veh": v}
                if self.actuator is not None:
                    self.actuator.locked.add(tls)
                if p in info.green_phases:                    # end the current green through its yellow
                    nxt = (p + 1) % len(info.states)
                    api.trafficlight.setPhase(tls, nxt)
                    api.trafficlight.setPhaseDuration(tls, info.durations[nxt])
                self.log.append({"time": t, "tls": tls, "vehicle": v, "action": "request", "from_phase": p, "target_phase": target})
            elif m["stage"] == "clearing":
                if p in info.green_phases and p == m["target"]:
                    m.update(stage="serving", since=t)
                elif p not in info.green_phases and obs.green_elapsed[tls] >= info.durations[p] - 1e-6:
                    api.trafficlight.setPhase(tls, m["target"])
                    api.trafficlight.setPhaseDuration(tls, self.max_hold)
                    m.update(stage="serving", since=t)
                    self.log.append({"time": t, "tls": tls, "vehicle": m["veh"], "action": "serve", "from_phase": p,
                                     "target_phase": m["target"]})
                elif p in info.green_phases:                  # program moved to another green meanwhile: clear it too
                    if obs.green_elapsed[tls] >= self.min_green:
                        nxt = (p + 1) % len(info.states)
                        api.trafficlight.setPhase(tls, nxt)
                        api.trafficlight.setPhaseDuration(tls, info.durations[nxt])
            elif m["stage"] == "serving":
                still = tls in wanted and wanted[tls][0] == m["veh"]
                if (not still and t - m["since"] >= self.min_green) or t - m["since"] >= self.max_hold:
                    nxt = (m["target"] + 1) % len(info.states)    # continue the program with the following yellow
                    api.trafficlight.setPhase(tls, nxt)
                    api.trafficlight.setPhaseDuration(tls, info.durations[nxt])
                    self.log.append({"time": t, "tls": tls, "vehicle": m["veh"], "action": "release",
                                     "held_s": round(t - m["since"], 1)})
                    self.mode.pop(tls)
                    if self.actuator is not None:
                        self.actuator.locked.discard(tls)
