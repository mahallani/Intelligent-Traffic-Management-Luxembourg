"""Prediction agent: forecasts the number of halted vehicles at each signal `horizon_s` ahead.

Model: damped linear trend over the last `window_s` seconds of samples (no training needed),
compared at the end of the run with the persistence baseline (forecast = current value).
SIMULATED data only. This is NOT the real-data forecasting task B, which is not trainable with
the CITA data collected so far (max 2 observations per sensor)."""
from __future__ import annotations

import statistics as st
from collections import deque


class PredictionAgent:
    name = "prediction"

    def __init__(self, env, horizon_s: float = 60.0, window_s: float = 60.0, damping: float = 0.5):
        self.h, self.window, self.damping = horizon_s, window_s, damping
        self.hist = {t: deque() for t in env.tls}
        self.pending: list[tuple[float, str, float, float]] = []   # (target_time, tls, forecast, persistence)
        self.errors = {"model": [], "persistence": []}
        self.last_forecast: dict[str, float] = {}

    def update(self, obs, tls_lanes: dict[str, list[str]]):
        if not obs.fresh:
            return self.last_forecast
        t = obs.time
        for tls, lanes in tls_lanes.items():
            q = sum(obs.halting(l) for l in lanes)
            h = self.hist[tls]
            h.append((t, q))
            while h and h[0][0] < t - self.window:
                h.popleft()
            slope = 0.0
            if len(h) >= 3:
                ts, qs = [x[0] for x in h], [x[1] for x in h]
                mt, mq = st.mean(ts), st.mean(qs)
                den = sum((a - mt) ** 2 for a in ts)
                slope = sum((a - mt) * (b - mq) for a, b in zip(ts, qs)) / den if den else 0.0
            f = max(0.0, q + self.damping * slope * self.h)
            self.last_forecast[tls] = f
            # score the forecasts whose target time has been reached
            due = [x for x in self.pending if x[1] == tls and x[0] <= t + 1e-6]
            for (_tt, _tl, fc, pers) in due:
                self.errors["model"].append(abs(fc - q))
                self.errors["persistence"].append(abs(pers - q))
            self.pending = [x for x in self.pending if not (x[1] == tls and x[0] <= t + 1e-6)]
            self.pending.append((t + self.h, tls, f, float(q)))
        return self.last_forecast

    def scores(self) -> dict:
        m, p = self.errors["model"], self.errors["persistence"]
        return {"forecast_horizon_s": self.h, "n_scored": len(m),
                "mae_model_veh": round(st.mean(m), 3) if m else None,
                "mae_persistence_veh": round(st.mean(p), 3) if p else None}
