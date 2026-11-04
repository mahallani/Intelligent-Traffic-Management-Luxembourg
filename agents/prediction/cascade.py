"""Cascade multi-horizon prediction of congestion at the 4 Kirchberg signals (SIMULATED data only).

Indicator predicted: y_i(t+h) = mean number of HALTED vehicles on the incoming lanes of signal i during the
minute ending at t+h, for h = +5, +10, +15 min.

Cascade (dependent horizons):
    stage +5  : y5  = f5 (x)
    stage +10 : y10 = f10(x, y5_hat)
    stage +15 : y15 = f15(x, y5_hat, y10_hat)
Each stage is a ridge linear regression. To avoid leakage, the y_hat used to TRAIN a later stage are
out-of-fold predictions (folds = whole episodes), never predictions on the episode being fitted.

Features x at origin t (only past data, available online):
    own halted (last minute), own halted 5 min before, trend, halted at the neighbour signals along the
    avenue (spill-back / propagation), total halted, vehicles in the zone, time since 07:00, signal one-hot.

Transform (v2): halting-type features and targets are modelled as log(1+x) (errors grow with congestion);
predictions are transformed back with exp(x)-1. Chosen on a VALIDATION split of the training seeds
(fit 201-202, validate 203), not on the test seeds.

Baselines: persistence (y_hat = current minute) and historical profile (mean of the training targets for
the same signal, horizon and minute of the episode). Direct (non-cascade) models are fitted for comparison.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

TLS_CHAIN = ["-28692", "-23354", "-20484", "-29958"]      # order along Avenue J.F. Kennedy (SW -> NE)
HORIZONS = (300, 600, 900)
STEP = 60.0
BEGIN = 25200.0
FEATURES = ["own_now", "own_5min_ago", "own_trend", "neighbours_now", "total_now", "vehicles_now", "tau"] + \
           [f"is_{t}" for t in TLS_CHAIN] + ["bias"]


def neighbours(tls: str) -> list[str]:
    i = TLS_CHAIN.index(tls)
    return [TLS_CHAIN[j] for j in (i - 1, i + 1) if 0 <= j < len(TLS_CHAIN)]


def minute_means(times, halting: dict[str, list], vehicles, t: float, width: float = STEP):
    """Mean of the 5-s samples in (t - width, t]."""
    idx = [k for k, x in enumerate(times) if t - width < x <= t + 1e-6]
    if not idx:
        return None
    h = {tl: float(np.mean([halting[tl][k] for k in idx])) for tl in halting}
    v = float(np.mean([vehicles[k] for k in idx]))
    return h, v


def features_at(times, halting, vehicles, t: float):
    now = minute_means(times, halting, vehicles, t)
    if now is None:
        return None
    past = minute_means(times, halting, vehicles, t - 300) or now
    h, v = now
    hp, _ = past
    total = sum(h.values())
    rows = {}
    for tl in TLS_CHAIN:
        rows[tl] = [h[tl], hp[tl], h[tl] - hp[tl], sum(h[n] for n in neighbours(tl)), total, v, (t - BEGIN) / 3600.0] + \
                   [1.0 if tl == x else 0.0 for x in TLS_CHAIN] + [1.0]
    return rows


LOG_IDX = (0, 1, 3, 4, 5)        # own_now, own_5min_ago, neighbours_now, total_now, vehicles_now


def transform_x(x: list[float], kind: str) -> list[float]:
    if kind != "log1p":
        return list(x)
    z = list(x)
    for i in LOG_IDX:
        z[i] = float(np.log1p(max(0.0, x[i])))
    z[2] = z[0] - z[1]                                   # trend in log space
    return z


def ridge(X, y, lam=1.0):
    X, y = np.asarray(X, float), np.asarray(y, float)
    reg = lam * np.eye(X.shape[1])
    reg[-1, -1] = 0.0                                   # no penalty on the bias
    return np.linalg.solve(X.T @ X + reg, X.T @ y)


@dataclass
class CascadeModel:
    cascade: dict = field(default_factory=dict)        # horizon -> coefficients (len = n_features + previous stages)
    direct: dict = field(default_factory=dict)         # horizon -> coefficients
    profile: dict = field(default_factory=dict)        # "tls|h|minute" -> mean target
    meta: dict = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return self.meta.get("transform", "none")

    def _back(self, v: float) -> float:
        return max(0.0, float(np.expm1(v))) if self.kind == "log1p" else max(0.0, float(v))

    def predict(self, x: list[float]) -> dict[int, float]:
        """x = raw features (features_at); returns predictions in vehicles for +5/+10/+15 min."""
        z, out, prev = transform_x(x, self.kind), {}, []
        for h in HORIZONS:
            v = float(np.dot(z + prev, np.asarray(self.cascade[str(h)])))
            out[h] = self._back(v)
            prev = prev + [v]                            # the cascade passes the (model-space) prediction on
        return out

    def predict_direct(self, x: list[float]) -> dict[int, float]:
        z = transform_x(x, self.kind)
        return {h: self._back(float(np.dot(z, np.asarray(self.direct[str(h)])))) for h in HORIZONS}

    def predict_profile(self, tls: str, minute: int) -> dict[int, float | None]:
        return {h: self.profile.get(f"{tls}|{h}|{minute}") for h in HORIZONS}

    def save(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"cascade": self.cascade, "direct": self.direct, "profile": self.profile,
                                          "meta": self.meta, "features": FEATURES}, indent=0), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CascadeModel":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["cascade"], d["direct"], d["profile"], d["meta"])


def episode_samples(rows: list[dict]) -> list[dict]:
    """rows of queue_timeseries.csv -> list of (origin, tls, x, targets) with all horizons available."""
    times = [float(r["time_s"]) for r in rows]
    halting = {tl: [float(r[f"halting_{tl}"]) for r in rows] for tl in TLS_CHAIN}
    vehicles = [float(r["vehicles_in_network"]) for r in rows]
    out = []
    t = BEGIN + 360.0                                    # need 5 min of history + 1 min
    end = times[-1]
    while t + max(HORIZONS) <= end + 1e-6:
        feats = features_at(times, halting, vehicles, t)
        targets = {h: minute_means(times, halting, vehicles, t + h) for h in HORIZONS}
        if feats and all(targets.values()):
            for tl in TLS_CHAIN:
                out.append({"origin": t, "tls": tl, "x": feats[tl], "y": {h: targets[h][0][tl] for h in HORIZONS},
                            "minute": int((t - BEGIN) // 60)})
        t += STEP
    return out


def fit(episodes: list[list[dict]], lam: float = 1.0, n_folds: int = 5, transform: str = "log1p") -> CascadeModel:
    """episodes: list of episode_samples() outputs (TRAINING episodes only)."""
    m = CascadeModel(meta={"n_episodes": len(episodes), "n_samples": sum(len(e) for e in episodes), "lambda": lam,
                           "n_folds": n_folds, "horizons_s": list(HORIZONS), "transform": transform,
                           "indicator": "mean halted vehicles per signal"})
    fy = (lambda v: float(np.log1p(v))) if transform == "log1p" else (lambda v: float(v))
    allr = [{**r, "x": transform_x(r["x"], transform), "y": {h: fy(v) for h, v in r["y"].items()}, "y_raw": r["y"]}
            for e in episodes for r in e]
    X = [r["x"] for r in allr]
    for h in HORIZONS:
        m.direct[str(h)] = ridge(X, [r["y"][h] for r in allr], lam).tolist()
    # out-of-fold stage predictions (folds = whole episodes)
    fold_of = [i % n_folds for i, e in enumerate(episodes) for _ in e]
    oof = {h: np.zeros(len(allr)) for h in HORIZONS}
    for f in range(n_folds):
        tr = [i for i, fo in enumerate(fold_of) if fo != f]
        te = [i for i, fo in enumerate(fold_of) if fo == f]
        if not te:
            continue
        prev_tr, prev_te = [[] for _ in tr], [[] for _ in te]
        for h in HORIZONS:
            coef = ridge([allr[i]["x"] + prev_tr[k] for k, i in enumerate(tr)], [allr[i]["y"][h] for i in tr], lam)
            pte = np.maximum(0, np.array([np.dot(allr[i]["x"] + prev_te[k], coef) for k, i in enumerate(te)]))
            ptr = np.maximum(0, np.array([np.dot(allr[i]["x"] + prev_tr[k], coef) for k, i in enumerate(tr)]))
            for k, i in enumerate(te):
                oof[h][i] = pte[k]
            prev_tr = [p + [ptr[k]] for k, p in enumerate(prev_tr)]
            prev_te = [p + [pte[k]] for k, p in enumerate(prev_te)]
    prev = [[] for _ in allr]
    for h in HORIZONS:
        m.cascade[str(h)] = ridge([r["x"] + prev[i] for i, r in enumerate(allr)], [r["y"][h] for r in allr], lam).tolist()
        prev = [p + [oof[h][i]] for i, p in enumerate(prev)]
    acc = {}
    for r in allr:
        for h in HORIZONS:
            acc.setdefault(f"{r['tls']}|{h}|{r['minute']}", []).append(r["y_raw"][h])
    m.profile = {k: float(np.mean(v)) for k, v in acc.items()}
    return m
