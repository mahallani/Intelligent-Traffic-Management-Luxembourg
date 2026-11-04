"""Intervention agent: applies the decisions to the 4 signals through TraCI, with safety rules:
* only green phases are held or ended; yellow phases always run their programmed duration;
* phase ORDER of the LuST program is kept (ADVANCE = go to the next phase, i.e. its yellow);
* min green (default 5 s) and max green are enforced here, whatever the decision agent says;
  max green of a phase = min(60 s, 2 x its programmed duration), the same bound as SUMO's
  actuated programs of strategy S1 (e.g. 20 s for the 10-s left-turn phases)."""
from __future__ import annotations

from ..decision.controllers import ADVANCE

HOLD_S = 3600.0


class TLSActuator:
    name = "intervention"

    def __init__(self, env, enabled: bool = True, min_green: float = 5.0, max_green: float = 60.0):
        self.env, self.enabled, self.min_green, self.max_green = env, enabled, min_green, max_green
        self.held: dict[str, int] = {}
        self.stats = {"advance": 0, "forced_max_green": 0, "refused_min_green": 0, "holds": 0}
        self.log: list[tuple] = []   # (time, tls, from_phase, to_phase, green_s, reason)
        self.locked: set[str] = set()  # signals temporarily under emergency-priority control

    def step(self, obs, actions: dict[str, int], explain: dict | None = None):
        if not self.enabled:
            return
        explain = explain or {}
        api = self.env.api
        for tid, info in self.env.tls.items():
            if tid in self.locked:                          # emergency priority has the signal
                self.held.pop(tid, None)
                continue
            p = obs.phase[tid]
            if api.trafficlight.getPhase(tid) != p:         # phase changed by another module (emergency priority)
                self.held.pop(tid, None)                    # after the observation: act on the next step only,
                continue                                    # never on a stale phase (fix 2026-10-12, see report)
            if p not in info.green_phases:
                self.held.pop(tid, None)
                continue
            if self.held.get(tid) != p:                     # new green phase: hold it until a decision ends it
                api.trafficlight.setPhaseDuration(tid, HOLD_S)
                self.held[tid] = p
                self.stats["holds"] += 1
            el = obs.green_elapsed[tid]
            if el >= min(self.max_green, 2 * info.durations[p]):
                self._advance(tid, info, p, obs, "max_green",
                              {"source": "sécurité : vert maximum atteint", "vert_s": round(el, 1),
                               "limite_s": min(self.max_green, 2 * info.durations[p])})
                self.stats["forced_max_green"] += 1
            elif actions.get(tid) == ADVANCE:
                if el < self.min_green:
                    self.stats["refused_min_green"] += 1
                else:
                    self._advance(tid, info, p, obs, "agent_decision", explain.get(tid))

    def _advance(self, tid, info, p, obs=None, reason="", explain=None):
        nxt = (p + 1) % len(info.states)
        if obs is not None:   # 7th field (2026-10-22): explanation recorded by the controller / the safety rule
            self.log.append((obs.time, tid, p, nxt, round(obs.green_elapsed[tid], 1), reason, explain))
        self.env.api.trafficlight.setPhase(tid, nxt)
        # the LuST logics are of type "actuated": setPhase alone keeps the previous switch time,
        # so the programmed duration of the next phase (the yellow) is set explicitly.
        self.env.api.trafficlight.setPhaseDuration(tid, info.durations[nxt])
        self.held.pop(tid, None)
        self.stats["advance"] += 1
