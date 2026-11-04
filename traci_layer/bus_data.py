"""
Buses / public transport - headway monitoring, bunching detection, bus priority (S1).

How LuST represents buses (verified in buslines.rou.xml / busstops.add.xml / vtypes.add.xml)
----------------------------------------------------------------------------------------------
* 2 240 bus trips, each an individual ``<vehicle type="bus">`` (vClass ``bus``, 12 m).
* 38 lines. The line is ONLY encoded in the vehicle id: ``AVL---_12_5`` = line
  ``AVL---_12``, trip 5. The ``line`` attribute is not set -> ``vehicle.getLine()`` returns
  ``""``; we derive the line from the id.
* 561 ``busStop`` elements (``busstops.add.xml``), each lists the lines serving it.
* Stops only have ``duration="20"``: NO timetable (no ``until`` / ``arrival``), so
  ``vehicle.getStopDelay`` returns -1 and "delay vs timetable" does not exist in LuST.
* No dedicated bus lanes (no lane restricts ``allow``/``disallow``).

What we can therefore measure
-----------------------------
Direct (TraCI): position, edge, lane, speed, waiting time, time loss, stop state
(``getStopState`` bit field), upcoming stops (``getStops``), people at stops (``busstop``).

Calculated (Cette métrique doit être calculée):
* ``delay_s``           = ``getTimeLoss`` (time lost vs. ideal driving, scheduled stops
                          excluded) -> proxy for delay because LuST has no timetable;
* ``dwell_time``        = departure - arrival at each bus stop;
* ``observed headway``  = time between two buses of the same line pattern (same stop
                          sequence = line variant + direction) at the same stop;
* ``planned headway``   = median gap between planned departures of that pattern
                          (from buslines.rou.xml; 1 800 s for all 76 LuST patterns);
* ``bunching``          = observed headway < ``bunching_ratio`` x planned headway.

If the team later adds ``until``/``arrival`` attributes to stops (timetable), schedule
adherence becomes directly available via ``vehicle.getStopDelay`` /
``getStopArrivalDelay`` -> "nécessite une configuration SUMO supplémentaire".
"""
from __future__ import annotations

import re
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from . import metrics as m

_TRIP_SUFFIX = re.compile(r"_(\d+)$")


def line_of(vehicle_id: str) -> str:
    """``AVL---_12_5`` -> ``AVL---_12`` (LuST naming convention)."""
    return _TRIP_SUFFIX.sub("", vehicle_id)


def pattern_of(line: str, stops: list[str]) -> str:
    """Identifier of a line + stop sequence. LuST lines have 2 patterns (one per direction);
    a few lines (e.g. AVL---_CN_4) have variants that start together and share stops, and
    two different lines share an identical stop sequence - so headways are computed per
    (line, stop sequence), not per (line, first stop)."""
    return line + "|" + ">".join(stops)


@dataclass
class PlannedTrip:
    vehicle_id: str
    line: str
    depart: float
    stops: list[str]
    direction: str           # first stop id of the trip
    pattern: str = ""        # stop sequence of the trip (identifies line variant + direction)
    planned_headway: Optional[float] = None


def load_bus_plan(route_files: Iterable[Path], bus_type_ids: Iterable[str] = ("bus",)) -> dict[str, PlannedTrip]:
    """Parse the planned bus trips (streaming parse, only ``<vehicle>`` of bus types)."""
    bus_types = set(bus_type_ids)
    plan: dict[str, PlannedTrip] = {}
    for f in route_files:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag == "vehicle":
                if el.get("type") in bus_types:
                    vid = el.get("id")
                    stops = [s.get("busStop") for s in el.iter("stop") if s.get("busStop")]
                    line = line_of(vid)
                    plan[vid] = PlannedTrip(vid, line, float(el.get("depart", 0)), stops,
                                            stops[0] if stops else "", pattern_of(line, stops))
                el.clear()
    groups: dict[str, list[PlannedTrip]] = defaultdict(list)
    for t in plan.values():
        groups[t.pattern].append(t)
    for trips in groups.values():
        gaps = m.headways([t.depart for t in trips])
        gaps = [g for g in gaps if g > 0]
        h = statistics.median(gaps) if gaps else None
        for t in trips:
            t.planned_headway = h
    return plan


@dataclass
class StopEvent:
    vehicle_id: str
    line: str
    stop_id: str
    arrival: float
    departure: Optional[float] = None
    headway: Optional[float] = None
    planned_headway: Optional[float] = None
    bunched: bool = False

    @property
    def dwell(self) -> Optional[float]:
        return None if self.departure is None else self.departure - self.arrival


@dataclass
class BusState:
    vehicle_id: str
    line: str
    pattern: str
    direction: str
    planned_headway: Optional[float]
    planned_stops: list[str]
    depart: float
    stops_done: int = 0
    at_stop: Optional[str] = None
    current_event: Optional[StopEvent] = None
    events: list[StopEvent] = field(default_factory=list)


class BusTracker:
    def __init__(self, api: Any, route_files: Iterable[Path] = (), bunching_ratio: float = 0.5,
                 geo: bool = True, bus_type_ids: Iterable[str] = ("bus",)):
        self.api = api
        self.bunching_ratio = bunching_ratio
        self.geo = geo
        self.plan = load_bus_plan(route_files, bus_type_ids) if route_files else {}
        self.active: dict[str, BusState] = {}
        self.events: list[StopEvent] = []
        self.last_arrival: dict[tuple[str, str], float] = {}   # (pattern, stop) -> time
        self._events_cursor = 0

    @property
    def planned_lines(self) -> int:
        return len({t.line for t in self.plan.values()})

    def on_departed(self, vehicle_id: str, time: float, preexisting: bool = False) -> None:
        """Register a bus. ``preexisting`` = already running when the collector started
        (e.g. after --load-state): its progress is read from the remaining stops."""
        p = self.plan.get(vehicle_id)
        if p is None:  # bus not in the plan (e.g. added by TraCI)
            stops = [s.stoppingPlaceID for s in self.api.vehicle.getStops(vehicle_id)]
            line = line_of(vehicle_id)
            p = PlannedTrip(vehicle_id, line, time, stops, stops[0] if stops else "", pattern_of(line, stops))
        bus = BusState(vehicle_id, p.line, p.pattern, p.direction, p.planned_headway, list(p.stops), time)
        if preexisting:
            remaining = self.api.vehicle.getStops(vehicle_id)  # upcoming stops, current one included
            bus.stops_done = max(0, len(p.stops) - len(remaining))
            state = self.api.vehicle.getStopState(vehicle_id)
            if (state & 1) and (state & 16) and remaining:
                # already dwelling: arrival time unknown -> no stop event for this stop
                bus.at_stop = remaining[0].stoppingPlaceID
        self.active[vehicle_id] = bus

    def on_arrived(self, vehicle_id: str) -> None:
        self.active.pop(vehicle_id, None)

    def update(self, latest: dict[str, dict], time: float) -> None:
        """Detect arrivals at / departures from bus stops (stop-state transitions)."""
        for vid, bus in self.active.items():
            v = latest.get(vid)
            if v is None:
                continue
            state = int(v.get("stop_state", 0))
            at_bus_stop = (state & 1) and (state & 16)
            if at_bus_stop and bus.at_stop is None:
                stops = self.api.vehicle.getStops(vid, 1)
                stop_id = stops[0].stoppingPlaceID if stops else "?"
                key = (bus.pattern, stop_id)
                prev = self.last_arrival.get(key)
                headway = (time - prev) if prev is not None else None
                ev = StopEvent(vid, bus.line, stop_id, time, headway=headway,
                               planned_headway=bus.planned_headway,
                               bunched=headway is not None and m.is_bunched(headway, bus.planned_headway, self.bunching_ratio))
                self.last_arrival[key] = time
                bus.at_stop, bus.current_event = stop_id, ev
                bus.events.append(ev)
                self.events.append(ev)
            elif not at_bus_stop and bus.at_stop is not None:
                if bus.current_event is not None:
                    bus.current_event.departure = time
                bus.at_stop, bus.current_event = None, None
                bus.stops_done += 1

    # ---------------------------------------------------------------- snapshot
    def snapshot(self, now: float, latest: dict[str, dict]) -> tuple[dict, list[dict]]:
        new_events = self.events[self._events_cursor:]
        self._events_cursor = len(self.events)
        rows = []
        for vid, bus in self.active.items():
            v = latest.get(vid)
            if v is None:
                continue
            x, y = v["position"]
            lon, lat = self.api.simulation.convertGeo(x, y) if self.geo else (None, None)
            nxt = bus.planned_stops[bus.stops_done] if bus.stops_done < len(bus.planned_stops) else None
            rows.append({
                "time": now, "bus_id": vid, "line_id": bus.line, "direction": bus.direction,
                "x": x, "y": y, "lon": lon, "lat": lat,
                "edge_id": v["edge_id"], "lane_id": v["lane_id"],
                "speed_kmh": m.kmh(v["speed"]), "waiting_time_s": v["waiting_time"],
                "delay_s": v["time_loss"],  # proxy (no timetable in LuST)
                "at_stop": bus.at_stop, "next_stop": bus.at_stop or nxt,
                "stops_done": bus.stops_done, "stops_planned": len(bus.planned_stops),
                "current_dwell_s": (now - bus.current_event.arrival) if bus.current_event else None,
                "planned_headway_s": bus.planned_headway,
                "last_headway_s": bus.events[-1].headway if bus.events else None,
            })
        all_hw = [e.headway for e in self.events if e.headway is not None]
        dwells = [e.dwell for e in self.events if e.dwell is not None]
        by_line: dict[str, dict] = defaultdict(lambda: {"buses": 0, "delay_sum": 0.0})
        for r in rows:
            by_line[r["line_id"]]["buses"] += 1
            by_line[r["line_id"]]["delay_sum"] += r["delay_s"]
        bunch_by_line: dict[str, int] = defaultdict(int)
        for e in self.events:
            if e.bunched:
                bunch_by_line[e.line] += 1
        summary = {
            "count": len(rows),
            "lines_active": len(by_line),
            "average_speed_kmh": m.safe_mean(r["speed_kmh"] for r in rows),
            "average_delay_s": m.safe_mean(r["delay_s"] for r in rows),
            "average_waiting_time_s": m.safe_mean(r["waiting_time_s"] for r in rows),
            "at_stop_now": sum(1 for r in rows if r["at_stop"]),
            "stop_events_total": len(self.events),
            "stop_events_since_last": len(new_events),
            "average_dwell_time_s": m.safe_mean(dwells),
            "average_headway_s": m.safe_mean(all_hw),
            "headway_cv": m.coefficient_of_variation(all_hw),
            "bunching_events_total": sum(1 for e in self.events if e.bunched),
            "bunching_events_since_last": sum(1 for e in new_events if e.bunched),
            "by_line": {
                ln: {"buses": d["buses"], "average_delay_s": d["delay_sum"] / d["buses"],
                     "bunching_events": bunch_by_line.get(ln, 0)}
                for ln, d in sorted(by_line.items())
            },
        }
        return summary, rows

    def stop_events_table(self) -> list[dict]:
        return [{
            "bus_id": e.vehicle_id, "line_id": e.line, "stop_id": e.stop_id,
            "arrival": e.arrival, "departure": e.departure, "dwell_s": e.dwell,
            "headway_s": e.headway, "planned_headway_s": e.planned_headway, "bunched": e.bunched,
        } for e in self.events]
