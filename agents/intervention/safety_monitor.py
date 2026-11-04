"""Safety monitor of the 4 signals, active in every run (it only READS the signal states).

Checks at every simulation step, per signal:
  * state_in_program : the displayed state is one of the states of the LuST program (no invented
                       combination -> no new conflicting movements; the programs themselves were checked
                       against SUMO's conflict matrix: scripts/simulation/check_signal_conflicts_v1.py)
  * green_to_red_without_yellow : a movement never goes from green (G/g) to red (r) without yellow (y)
  * min_green : a green phase that ends lasted at least `min_green` seconds (first, partial phase ignored)
  * yellow_duration : a yellow phase lasted its programmed duration (+-1 s); an overrun is flagged AS SOON AS
                      it happens (a yellow that never ends is caught, fix 2026-10-12)
  * all_red_duration : an all-red phase never lasts more than its programmed duration + 1 s
  * max_green : a green phase never lasts more than `max_green` seconds (adaptive strategies; the fixed
                programs are checked against their own durations)
Violations are counted and the first ones are kept with their time."""
from __future__ import annotations


class SafetyMonitor:
    name = "safety"

    def __init__(self, env, min_green: float = 5.0, max_green: float = 90.0):
        self.env, self.min_green, self.max_green = env, min_green, max_green
        self.prog_states = {t: set(i.states) for t, i in env.tls.items()}
        self.yellow_dur = {t: {s: d for s, d in zip(i.states, i.durations) if "y" in s.lower()} for t, i in env.tls.items()}
        self.red_dur = {t: {} for t in env.tls}
        for t, i in env.tls.items():
            for s, d in zip(i.states, i.durations):
                if "y" not in s.lower() and "g" not in s.lower():
                    self.red_dur[t][s] = max(d, self.red_dur[t].get(s, 0.0))
        self.overrun_reported: dict[str, bool] = {t: False for t in env.tls}
        self.prev: dict[str, str] = {}
        self.since: dict[str, float] = {}
        self.first: dict[str, bool] = {t: True for t in env.tls}
        self.counts = {"state_in_program": 0, "green_to_red_without_yellow": 0, "min_green": 0,
                       "yellow_duration": 0, "all_red_duration": 0, "max_green": 0}
        self.examples: list[dict] = []
        self.transitions = 0

    def _flag(self, kind, t, tls, detail):
        self.counts[kind] += 1
        if len(self.examples) < 20:
            self.examples.append({"check": kind, "time": t, "tls": tls, "detail": detail})

    @staticmethod
    def _green(s):
        return ("G" in s or "g" in s) and "y" not in s.lower()

    def step(self, t: float):
        api = self.env.api
        for tls in self.env.tls:
            st = api.trafficlight.getRedYellowGreenState(tls)
            if st not in self.prog_states[tls]:
                self._flag("state_in_program", t, tls, st)
            prev = self.prev.get(tls)
            if prev is None:
                self.prev[tls], self.since[tls] = st, t
                continue
            if self._green(st) and t - self.since[tls] > self.max_green and prev == st:
                self._flag("max_green", t, tls, f"{st} for {t - self.since[tls]:.0f} s")
                self.since[tls] = t                       # report once per excess period
            if st == prev:
                if not self.overrun_reported[tls]:
                    lim = self.yellow_dur[tls].get(st, self.red_dur[tls].get(st))
                    if lim is not None and t - self.since[tls] > lim + 1.0:
                        kind = "yellow_duration" if st in self.yellow_dur[tls] else "all_red_duration"
                        self._flag(kind, t, tls, f"{st} still shown after {t - self.since[tls]:.0f} s (programmed {lim:.0f})")
                        self.overrun_reported[tls] = True
                continue
            self.transitions += 1
            dur = t - self.since[tls]
            for i, (a, b) in enumerate(zip(prev, st)):
                if a in "Gg" and b in "rR":
                    self._flag("green_to_red_without_yellow", t, tls, f"link {i}: {prev} -> {st}")
                    break
            if not self.first[tls]:
                if self._green(prev) and dur < self.min_green - 1e-6:
                    self._flag("min_green", t, tls, f"{prev} lasted {dur:.0f} s")
                if prev in self.yellow_dur[tls] and abs(dur - self.yellow_dur[tls][prev]) > 1.0 and not self.overrun_reported[tls]:
                    self._flag("yellow_duration", t, tls, f"{prev} lasted {dur:.0f} s instead of {self.yellow_dur[tls][prev]:.0f}")
            self.first[tls] = False
            self.overrun_reported[tls] = False
            self.prev[tls], self.since[tls] = st, t

    def summary(self) -> dict:
        return {"transitions_checked": self.transitions, "violations": dict(self.counts),
                "total_violations": sum(self.counts.values()), "examples": self.examples,
                "limits": {"min_green_s": self.min_green, "max_green_s": self.max_green}}
