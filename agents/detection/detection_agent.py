"""Detection agent: flags persistent congestion on the incoming lanes of the 4 signals.

Two documented rules per incoming lane:
* "congestion": at least `min_halting` vehicles halted in every sample during `min_duration_s`;
* "stalled":    a vehicle has been stopped continuously for `stall_s` seconds (longer than any normal
                red time: the longest LuST cycle here is 96 s), i.e. the lane does not discharge.
An alert is opened when a rule holds and closed when the lane is back to normal.

Option `gate_with_forecast` (v2): the "congestion" rule is only raised when the signal's halted vehicles
exceed what the cascade prediction expected 5 minutes earlier by at least `residual_min` vehicles, i.e. the
congestion was NOT anticipated (recurrent congestion is predicted, an incident is not). "stalled" is unchanged.

Option `discharge_rule` (v3, replaces the "congestion" rule): a lane is "blocked" when, over the last
`discharge_window_s` (90 s), it had at least `min_green_s` (20 s) of green, at least `min_halting_blocked` (3)
halted vehicles at every sample, and NO vehicle left it. A congested lane still discharges at green; a blocked
lane does not. Thresholds fixed a priori (not tuned on the evaluation seeds). On SIMULATED data only: the real CITA data contain no
labelled incidents (see data/reports/readiness_by_objective_v1.md, objective A = not trainable),
so this rule is not a trained model and its accuracy is only measured against incidents
injected in the simulation (ground truth known)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Alert:
    lane: str
    tls: str
    start: float          # time the condition started
    raised: float         # time the alert was raised (start + min_duration)
    end: float | None = None
    max_halting: int = 0
    rule: str = "congestion"


class DetectionAgent:
    name = "detection"

    def __init__(self, env, min_halting: int = 8, min_duration_s: float = 60.0, stall_s: float = 150.0,
                 gate_with_forecast: bool = False, residual_min: float = 5.0, discharge_rule: bool = False,
                 discharge_window_s: float = 90.0, min_green_s: float = 20.0, min_halting_blocked: int = 3):
        self.min_halting, self.min_duration, self.stall_s = min_halting, min_duration_s, stall_s
        self.gate, self.residual_min = gate_with_forecast, residual_min
        self.tls_lanes = {tid: list(i.in_lanes) for tid, i in env.tls.items()}
        self.suppressed = 0
        self.discharge = discharge_rule
        self.dw, self.min_green, self.min_hb = discharge_window_s, min_green_s, min_halting_blocked
        self.green_s: dict[str, float] = {}
        self.window: dict[str, list] = {}           # lane -> [(t, halting, departures, green_seconds_since_last)]
        self._last_t = None
        self.lane_tls = {l: tid for tid, i in env.tls.items() for l in i.in_lanes}
        self.since: dict[str, float] = {}
        self.open: dict[str, Alert] = {}
        self.alerts: list[Alert] = []

    def update(self, obs, predictor=None) -> list[Alert]:
        if self.discharge and obs.green_lanes is not None:
            dt = 0.0 if self._last_t is None else obs.time - self._last_t
            self._last_t = obs.time
            for lane in self.lane_tls:
                if lane in obs.green_lanes:
                    self.green_s[lane] = self.green_s.get(lane, 0.0) + dt
        if not obs.fresh:
            return []
        new = []
        unexpected = {}
        if self.gate and predictor is not None:
            for tid, lanes in self.tls_lanes.items():
                exp = predictor.expected_now(tid, obs.time)
                cur = sum(obs.halting(l) for l in lanes)
                unexpected[tid] = exp is not None and cur - exp >= self.residual_min
        for lane, tls in self.lane_tls.items():
            h = obs.halting(lane)
            stalled = obs.max_wait.get(lane, 0.0) >= self.stall_s
            congested = False
            if self.discharge:
                w = self.window.setdefault(lane, [])
                w.append((obs.time, h, obs.departures.get(lane, 0), self.green_s.pop(lane, 0.0)))
                while w and w[0][0] <= obs.time - self.dw:
                    w.pop(0)
                full = len(w) >= int(self.dw / 5) - 1
                congested = full and all(x[1] >= self.min_hb for x in w) and sum(x[2] for x in w[1:]) == 0 \
                    and sum(x[3] for x in w[1:]) >= self.min_green
                if congested:
                    self.since.setdefault(lane, w[0][0])
                else:
                    self.since.pop(lane, None)
            elif h >= self.min_halting:
                self.since.setdefault(lane, obs.time)
                congested = obs.time - self.since[lane] >= self.min_duration
                if congested and self.gate and not unexpected.get(tls, False):
                    congested = False                     # congestion was predicted: not an incident
                    self.suppressed += 1
            else:
                self.since.pop(lane, None)
            if congested or stalled:
                if lane in self.open:
                    self.open[lane].max_halting = max(self.open[lane].max_halting, h)
                else:
                    start = obs.time - obs.max_wait.get(lane, 0.0) if stalled and not congested else self.since[lane]
                    a = Alert(lane, tls, start, obs.time, max_halting=h,
                              rule="stalled" if stalled and not congested else ("blocked" if self.discharge else "congestion"))
                    self.open[lane] = a
                    self.alerts.append(a)
                    new.append(a)
            elif lane in self.open:
                self.open.pop(lane).end = obs.time
        return new
