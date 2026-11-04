"""Collection agent: reads the simulation through TraCI and publishes an Observation.

Every step it reads the 4 signal phases (cheap); every `sample_every` seconds it also reads the
halting / vehicle counts and jam length of every incoming and outgoing lane of the 4 signals.
The time series of samples is kept for the KPIs (SIMULATED data)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Observation:
    time: float
    phase: dict[str, int]
    green_elapsed: dict[str, float]
    lanes: dict[str, tuple[int, int, float]] = field(default_factory=dict)  # lane -> (halting, vehicles, jam_m)
    fresh: bool = False                                                    # lanes read at this step
    max_wait: dict[str, float] = field(default_factory=dict)              # in-lane -> longest continuous stop (s)
    green_lanes: frozenset = frozenset()                                    # in-lanes with a green (G/g) link now
    departures: dict[str, int] = field(default_factory=dict)              # in-lane -> vehicles that left since last sample

    def halting(self, lane: str) -> int:
        return self.lanes.get(lane, (0, 0, 0.0))[0]

    def vehicles(self, lane: str) -> int:
        return self.lanes.get(lane, (0, 0, 0.0))[1]


class CollectionAgent:
    name = "collection"

    def __init__(self, env, sample_every: float = 5.0):
        self.env, self.sample_every = env, sample_every
        self.lanes = sorted({l for i in env.tls.values() for l in i.in_lanes + i.out_lanes})
        self.in_lanes = sorted({l for i in env.tls.values() for l in i.in_lanes})
        self._max_wait: dict[str, float] = {}
        self.last_phase: dict[str, int] = {}
        self.phase_start: dict[str, float] = {}
        self.samples: list[dict] = []
        self._last_lanes: dict = {}
        self._next_sample = None
        self._lane_links = {tid: [[i for (i, _o, _v) in lk] for lk in env.api.trafficlight.getControlledLinks(tid)]
                            for tid in env.tls}
        self._prev_ids: dict[str, set] = {}
        self._departures: dict[str, int] = {}

    def _alive_on(self, edge: str) -> set:
        return set(self.env.api.edge.getLastStepVehicleIDs(edge))

    def observe(self) -> Observation:
        api, t = self.env.api, self.env.time
        phase = {}
        for tid in self.env.tls:
            p = api.trafficlight.getPhase(tid)
            if self.last_phase.get(tid) != p:
                self.phase_start[tid] = t
                self.last_phase[tid] = p
            phase[tid] = p
        elapsed = {tid: t - self.phase_start[tid] for tid in phase}
        green = set()
        for tid, links in self._lane_links.items():
            st = api.trafficlight.getRedYellowGreenState(tid)
            for idx, lanes_in in enumerate(links):
                if idx < len(st) and st[idx] in "Gg":
                    green.update(lanes_in)
        fresh = self._next_sample is None or t >= self._next_sample
        if fresh:
            lanes = {}
            for l in self.lanes:
                h = api.lane.getLastStepHaltingNumber(l)
                n = api.lane.getLastStepVehicleNumber(l)
                jam = h * (api.lane.getLastStepLength(l) + 2.5) if h else 0.0   # mean length + SUMO default minGap
                lanes[l] = (h, n, jam)
            self._last_lanes = lanes
            self._max_wait = {l: max((api.vehicle.getWaitingTime(v) for v in api.lane.getLastStepVehicleIDs(l)), default=0.0)
                              if lanes[l][0] else 0.0 for l in self.in_lanes}
            deps = {}
            for l in self.in_lanes:
                ids = set(api.lane.getLastStepVehicleIDs(l))
                edge = l.rsplit("_", 1)[0]
                gone = self._prev_ids.get(l, set()) - ids
                # a vehicle that only changed lane is still on the same edge: not a departure through the stop line
                deps[l] = sum(1 for v in gone if v not in self._alive_on(edge)) if gone else 0
                self._prev_ids[l] = ids
            self._departures = deps
            self._next_sample = t + self.sample_every
            by_tls = {tid: sum(self._last_lanes[l][0] for l in info.in_lanes) for tid, info in self.env.tls.items()}
            self.samples.append({"time": t, "halting_total": sum(by_tls.values()), "halting_by_tls": by_tls,
                                 "queue_m_total": round(sum(self._last_lanes[l][2] for tid, info in self.env.tls.items()
                                                            for l in info.in_lanes), 1),
                                 "vehicles_in_network": api.vehicle.getIDCount()})
        return Observation(t, phase, elapsed, dict(self._last_lanes), fresh, dict(self._max_wait), frozenset(green),
                           dict(self._departures) if fresh else {})
