"""Decision agents for the 4 signals. Action space per signal at a decision point:
KEEP the current green, or ADVANCE to the next phase of the LuST program (the actuator then
plays the programmed yellow). Phase ORDER and yellow times are never changed.

* FixedTimeController    - reference: LuST programs untouched (no decision taken)
* DemandGapController    - rule-based demand-responsive control: end the green when its lanes are
                           (almost) empty and another phase is waiting (thresholds tuned on seed 50)
* MaxPressureController  - rule-based adaptive control (pressure = halted upstream - halted downstream)
* QLearningController    - tabular Q-learning (RL), one table per signal, trained in SUMO only;
                           falls back to the DemandGap rule in states it has not learned enough
"""
from __future__ import annotations

import json
import random
from pathlib import Path

KEEP, ADVANCE = 0, 1


def phase_lanes(info, p):
    ins = sorted({i for i, _ in info.phase_links[p]})
    outs = sorted({o for _, o in info.phase_links[p]})
    return ins, outs


class BaseController:
    adaptive = True
    name = "base"

    def __init__(self, min_green: float = 5.0, decision_interval: float = 5.0):
        self.min_green, self.decision_interval = min_green, decision_interval
        self.last_explain: dict[str, dict] = {}   # tls -> inputs actually used for the last decision (2026-10-22)

    def decision_points(self, obs, env):
        if not obs.fresh:
            return []
        return [tid for tid, info in env.tls.items()
                if obs.phase[tid] in info.green_phases and obs.green_elapsed[tid] >= self.min_green]

    def decide(self, obs, env, forecasts=None) -> dict[str, int]:
        return {}

    def end_episode(self, obs, env):
        pass


class FixedTimeController(BaseController):
    adaptive = False
    name = "S0_fixed_time"

    def decision_points(self, obs, env):
        return []


def green_demand(obs, info, tid):
    """(halted, moving) vehicles on the lanes served by the current green, max halted on another green."""
    cur = obs.phase[tid]
    lanes = phase_lanes(info, cur)[0]
    qc = sum(obs.halting(l) for l in lanes)
    mc = sum(obs.vehicles(l) - obs.halting(l) for l in lanes)
    qo = max((sum(obs.halting(l) for l in phase_lanes(info, p)[0]) for p in info.green_phases if p != cur), default=0)
    return qc, mc, qo


class DemandGapController(BaseController):
    """ADVANCE when at most `max_halted` vehicles are halted and at most `max_moving` are moving on the
    lanes of the current green, and at least one vehicle waits on another phase. Max green is enforced by
    the actuator (2 x programmed duration, <= 60 s). Thresholds (1, 2) chosen on tuning seed 50 among
    (0,0), (0,1), (1,2), (2,3); evaluation seeds 1-3 were not used for tuning."""
    name = "S2_demand_gap"

    def __init__(self, max_halted: int = 1, max_moving: int = 2, **kw):
        super().__init__(**kw)
        self.max_halted, self.max_moving = max_halted, max_moving

    def rule(self, obs, info, tid):
        qc, mc, qo = green_demand(obs, info, tid)
        a = ADVANCE if (qc <= self.max_halted and mc <= self.max_moving and qo > 0) else KEEP
        self.last_explain[tid] = {"source": "règle S2", "arrêtés_vert": qc, "en_mouvement_vert": mc, "attente_autre_phase": qo,
                                  "seuils": [self.max_halted, self.max_moving], "action": "passer" if a == ADVANCE else "garder"}
        return a

    def decide(self, obs, env, forecasts=None):
        return {tid: self.rule(obs, env.tls[tid], tid) for tid in self.decision_points(obs, env)}


class ForecastGapController(DemandGapController):
    """S2F - demand-gap rule INFORMED BY THE CASCADE PREDICTION: when the +5 min forecast of halted vehicles
    at a signal exceeds the current minute by at least `rise` vehicles (congestion building up), greens are
    ended earlier (gap thresholds 2/3 instead of 1/2: shorter cycles, the other approaches are served sooner).
    Otherwise it behaves exactly like S2. Chosen on tuning seeds 50 and 60 among rise in {3, 6} x thresholds
    {(0,1), (2,3)}: mean travel time 119.8 s vs 120.4 s for S2 on the same seeds (difference within noise)."""
    name = "S2F_forecast_gap"

    def __init__(self, rise: float = 3.0, rising_thresholds: tuple = (2, 3), **kw):
        super().__init__(**kw)
        self.rise, self.rising_thresholds = rise, rising_thresholds
        self.stats = {"decisions": 0, "decisions_with_forecast": 0, "decisions_rising": 0}

    def decide(self, obs, env, forecasts=None):
        acts = {}
        for tid in self.decision_points(obs, env):
            info = env.tls[tid]
            f = (forecasts or {}).get(tid)
            rising = bool(f) and f[300] - f["now"] >= self.rise
            qc, mc, qo = green_demand(obs, info, tid)
            mh, mm = self.rising_thresholds if rising else (self.max_halted, self.max_moving)
            acts[tid] = ADVANCE if (qc <= mh and mc <= mm and qo > 0) else KEEP
            self.last_explain[tid] = {"source": "règle S2F", "arrêtés_vert": qc, "en_mouvement_vert": mc, "attente_autre_phase": qo,
                                      "prévision_maintenant": round(f["now"], 2) if f else None,
                                      "prévision_5min": round(f[300], 2) if f else None, "file_qui_monte": rising,
                                      "seuils": [mh, mm], "action": "passer" if acts[tid] == ADVANCE else "garder"}
            self.stats["decisions"] += 1
            self.stats["decisions_with_forecast"] += bool(f)
            self.stats["decisions_rising"] += rising
        return acts


class MaxPressureController(BaseController):
    """Advance when the NEXT green phase of the (unchanged) LuST sequence has a higher pressure than
    the current one by more than `margin` vehicles. Parameters were chosen on a tuning seed (50)
    that is not used for the evaluation (seeds 1-3)."""
    name = "S2b_max_pressure"

    def __init__(self, min_green: float = 5.0, margin: float = 2.0, compare: str = "next", **kw):
        super().__init__(min_green=min_green, **kw)
        self.margin, self.compare = margin, compare

    def pressure(self, obs, info, p):
        ins, outs = phase_lanes(info, p)
        return sum(obs.halting(l) for l in ins) - sum(obs.halting(l) for l in outs)

    def decide(self, obs, env, forecasts=None):
        acts = {}
        for tid in self.decision_points(obs, env):
            info = env.tls[tid]
            cur = obs.phase[tid]
            pc = self.pressure(obs, info, cur)
            if self.compare == "next":
                g = info.green_phases
                other = self.pressure(obs, info, g[(g.index(cur) + 1) % len(g)])
            else:
                other = max((self.pressure(obs, info, p) for p in info.green_phases if p != cur), default=pc)
            acts[tid] = ADVANCE if other > pc + self.margin else KEEP
            self.last_explain[tid] = {"source": "max-pressure", "pression_phase_actuelle": pc, "pression_autre_phase": other,
                                      "marge": self.margin, "action": "passer" if acts[tid] == ADVANCE else "garder"}
        return acts


def _bin(x, edges):
    for i, e in enumerate(edges):
        if x <= e:
            return i
    return len(edges)


class QLearningController(BaseController):
    """Independent tabular Q-learning per signal (SMDP approximation: one transition = from a decision
    point to the next decision point of the same signal). Reward (semi-Markov) = -(sum of the halted
    vehicles on all incoming lanes of that signal over the 5-s samples between the two decisions) / 10,
    discount gamma^(number of samples), so a long interval costs proportionally more.
    The greedy policy trusts a Q-value only when BOTH actions were tried at least `min_visits` times in
    that state; otherwise it falls back to the programmed LuST duration (no invented knowledge)."""
    name = "S3_rl_qlearning"
    Q_EDGES = (0, 2, 5, 10)
    T_EDGES = (10, 20, 40)

    def __init__(self, qtable_path: Path | None = None, train: bool = False, epsilon: float = 0.0,
                 alpha: float = 0.1, gamma: float = 0.9, seed: int = 0, min_visits: int = 3,
                 fallback: str = "demand_gap", **kw):
        super().__init__(**kw)
        self.fallback = fallback
        self._gap = DemandGapController()
        self.train, self.eps, self.alpha, self.gamma, self.min_visits = train, epsilon, alpha, gamma, min_visits
        self.n: dict[str, list[int]] = {}
        self.acc: dict[str, float] = {}
        self.k: dict[str, int] = {}
        self.rng = random.Random(seed)
        self.q: dict[str, list[float]] = {}
        self.meta = {"episodes_trained": 0, "train_seeds": [], "train_scales": [], "fallback": fallback}
        self.qtable_path = Path(qtable_path) if qtable_path else None
        if self.qtable_path and self.qtable_path.exists():
            d = json.loads(self.qtable_path.read_text(encoding="utf-8"))
            self.q, self.meta, self.n = d["q"], d["meta"], d.get("n", {})
        self.prev: dict[str, tuple[str, int]] = {}
        self.stats = {"decisions": 0, "unseen_states": 0, "fallback_decisions": 0, "explorations": 0, "updates": 0}

    M_EDGES = (0, 2, 5)

    def state(self, obs, info, tid):
        """(green phase, halted on current green lanes, max halted on another green phase,
        moving vehicles on current green lanes, green elapsed) - all binned."""
        cur = obs.phase[tid]
        g = info.green_phases.index(cur)
        lanes = phase_lanes(info, cur)[0]
        qc = sum(obs.halting(l) for l in lanes)
        mc = sum(obs.vehicles(l) - obs.halting(l) for l in lanes)
        qo = max((sum(obs.halting(l) for l in phase_lanes(info, p)[0]) for p in info.green_phases if p != cur), default=0)
        return (f"{tid}|{g}|{_bin(qc, self.Q_EDGES)}|{_bin(qo, self.Q_EDGES)}|{_bin(mc, self.M_EDGES)}|"
                f"{_bin(obs.green_elapsed[tid], self.T_EDGES)}")

    def reward(self, obs, info):
        return -sum(obs.halting(l) for l in info.in_lanes) / 10.0

    def decide(self, obs, env, forecasts=None):
        acts = {}
        if obs.fresh:
            for tid in self.prev:
                self.acc[tid] = self.acc.get(tid, 0.0) + self.reward(obs, env.tls[tid])
                self.k[tid] = self.k.get(tid, 0) + 1
        for tid in self.decision_points(obs, env):
            info = env.tls[tid]
            s = self.state(obs, info, tid)
            if self.train and tid in self.prev:
                ps, pa = self.prev[tid]
                qv = self.q.setdefault(ps, [0.0, 0.0])
                target = self.acc.get(tid, 0.0) + self.gamma ** self.k.get(tid, 1) * max(self.q.get(s, [0.0, 0.0]))
                qv[pa] += self.alpha * (target - qv[pa])
                self.stats["updates"] += 1
            qv_now, vis = self.q.get(s), self.n.get(s, [0, 0])
            if self.train and self.rng.random() < self.eps:
                a = self.rng.choice((KEEP, ADVANCE))
                self.stats["explorations"] += 1
                src = "exploration (hasard)"
            elif s in self.q and min(self.n.get(s, [0, 0])) >= self.min_visits and self.q[s][0] != self.q[s][1]:
                a = KEEP if self.q[s][0] > self.q[s][1] else ADVANCE
                src = "table apprise"
            else:   # not enough experience in this state: fallback rule (no invented knowledge)
                if s not in self.q:
                    self.stats["unseen_states"] += 1
                self.stats["fallback_decisions"] += 1
                if self.fallback == "demand_gap":
                    a = self._gap.rule(obs, info, tid)
                else:
                    a = ADVANCE if obs.green_elapsed[tid] >= info.durations[obs.phase[tid]] else KEEP
                src = "règle de secours S2 (situation " + ("jamais vue" if qv_now is None else "trop peu vue") + ")"
            parts = s.split("|")
            ex = {"source": src, "situation": {"phase_verte": parts[1], "file_servie": parts[2], "file_autre": parts[3],
                                               "en_mouvement": parts[4], "durée_vert": parts[5]},
                  "q_garder": round(qv_now[0], 3) if qv_now else None, "q_passer": round(qv_now[1], 3) if qv_now else None,
                  "visites_garder_passer": list(vis), "action": "passer" if a == ADVANCE else "garder"}
            if src.startswith("règle"):
                ex["règle_S2"] = {k: v for k, v in self._gap.last_explain.get(tid, {}).items() if k != "source"}
            self.last_explain[tid] = ex
            if self.train:
                self.n.setdefault(s, [0, 0])[a] += 1
                self.q.setdefault(s, [0.0, 0.0])
            self.prev[tid] = (s, a)
            self.acc[tid], self.k[tid] = 0.0, 0
            acts[tid] = a
            self.stats["decisions"] += 1
        return acts

    def end_episode(self, obs, env):
        self.prev.clear()
        self.acc.clear()
        self.k.clear()

    def save(self, path: Path, seed: int, scale: float):
        self.meta["episodes_trained"] += 1
        self.meta["train_seeds"].append(seed)
        self.meta["train_scales"].append(scale)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps({"meta": self.meta, "q": self.q, "n": self.n}, indent=0), encoding="utf-8")
        tmp.replace(path)
