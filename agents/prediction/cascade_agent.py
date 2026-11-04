"""Online cascade prediction agent: every minute (after 6 min of history) it predicts, for each signal,
the halted vehicles at +5, +10 and +15 min with the trained CascadeModel, publishes them to the decision
and detection agents, and logs forecast / observed value / error when the target time is reached.
SIMULATED data only (model trained on SUMO episodes, see scripts/simulation/train_eval_cascade.py)."""
from __future__ import annotations

from pathlib import Path

from .cascade import BEGIN, HORIZONS, STEP, TLS_CHAIN, CascadeModel, features_at, minute_means

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "sumo/lust_4_intersections/output/experiments_v1/prediction/cascade_model_v2.json"


class CascadePredictionAgent:
    name = "prediction_cascade"

    def __init__(self, env, collection_agent, model_path: Path = DEFAULT_MODEL):
        self.model = CascadeModel.load(model_path)
        self.model_path = Path(model_path)
        self.col = collection_agent
        self.latest: dict[str, dict] = {}          # tls -> {"origin": t, "now": v, 300: v, 600: v, 900: v}
        self.history: dict[str, dict[float, float]] = {t: {} for t in TLS_CHAIN}   # tls -> {target_time: forecast +5 min}
        self.pending: list[tuple] = []             # (target_t, origin, tls, h, forecast, persistence)
        self.log: list[dict] = []
        self.next_origin = BEGIN + 360.0

    def _arrays(self):
        s = self.col.samples
        times = [x["time"] for x in s]
        halting = {t: [x["halting_by_tls"][t] for x in s] for t in TLS_CHAIN}
        vehicles = [x["vehicles_in_network"] for x in s]
        return times, halting, vehicles

    def update(self, obs) -> dict:
        if not obs.fresh or obs.time + 1e-6 < self.next_origin:
            return self.latest
        t = obs.time
        times, halting, vehicles = self._arrays()
        # score forecasts whose target minute is complete
        due = [p for p in self.pending if p[0] <= t + 1e-6]
        self.pending = [p for p in self.pending if p[0] > t + 1e-6]
        for (tt, origin, tls, h, fc, pers) in due:
            mm = minute_means(times, halting, vehicles, tt)
            if mm is None:
                continue
            obs_v = mm[0][tls]
            self.log.append({"origin_s": origin, "target_s": tt, "tls": tls, "horizon_min": h // 60, "forecast": round(fc, 3),
                             "observed": round(obs_v, 3), "error": round(fc - obs_v, 3), "persistence": round(pers, 3),
                             "error_persistence": round(pers - obs_v, 3)})
        feats = features_at(times, halting, vehicles, t)
        if feats:
            for tls, x in feats.items():
                pred = self.model.predict(x)
                self.latest[tls] = {"origin": t, "now": x[0], **pred}
                self.history[tls][t + 300] = pred[300]
                for h in HORIZONS:
                    self.pending.append((t + h, t, tls, h, pred[h], x[0]))
        self.next_origin = t + STEP
        return self.latest

    def expected_now(self, tls: str, t: float):
        """Forecast made 5 min ago for the current minute (None if not available)."""
        cands = [k for k in self.history[tls] if abs(k - t) <= STEP / 2 + 1e-6]
        return self.history[tls][cands[0]] if cands else None

    def scores(self) -> dict:
        out = {"model": self.model_path.name, "transform": self.model.kind, "n_scored": len(self.log)}
        for h in HORIZONS:
            rows = [r for r in self.log if r["horizon_min"] == h // 60]
            if rows:
                out[f"mae_cascade_{h // 60}min"] = round(sum(abs(r["error"]) for r in rows) / len(rows), 3)
                out[f"mae_persistence_{h // 60}min"] = round(sum(abs(r["error_persistence"]) for r in rows) / len(rows), 3)
        return out
