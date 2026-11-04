"""
Emergency vehicles (BO4, S2 Emergency Priority).

LuST check (verified): the scenario contains NO emergency vehicle - only ``passenger1..5``
cars and ``bus`` (vtypes.add.xml, 288 250 vehicles over 24 h). No lane allows/forbids
``emergency`` specifically. Emergency vehicles must therefore be ADDED by the project:

1. vehicle types: ``sumo/additional/emergency_vtypes.add.xml`` (vClass ``emergency``,
   optional ``bluelight`` device = siren/rescue lane) loaded as an extra additional file;
2. the vehicle itself: :func:`spawn_emergency_vehicle` (``simulation.findRoute`` +
   ``route.add`` + ``vehicle.add``) at the incident time, with the SAME id / route /
   depart in every scenario S0..S4 so that results are comparable.

Identification rule: vClass ``emergency`` OR type id in ``CollectorConfig.emergency_type_ids``.

Direct (TraCI): position, edge, lane, speed, waiting time, route (``getRoute``), time loss,
next traffic lights (``getNextTLS``), departure (observed).
Calculated: travel time = arrival - departure; free-flow time = sum(length / ideal speed)
over the route edges AND the junction internal lanes; delay = travel time - free-flow
time (close to SUMO's own ``getTimeLoss``); mission time = travel time + insertion delay;
number of stops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from . import metrics as m


@dataclass
class EmergencyVehicleSpec:
    """Description of an emergency mission injected in the simulation."""

    vehicle_id: str
    from_edge: str
    to_edge: str
    depart: str | float = "now"
    type_id: str = "emergency_bluelight"
    depart_lane: str = "best"
    depart_speed: str = "max"


def ensure_emergency_type(api: Any, type_id: str) -> str:
    """Make sure ``type_id`` exists. If the additional file was not loaded, create a
    basic emergency type from the default type (without bluelight device)."""
    if type_id in api.vehicletype.getIDList():
        return type_id
    vt = api.vehicletype
    vt.copy("DEFAULT_VEHTYPE", type_id)
    vt.setVehicleClass(type_id, "emergency")
    vt.setShapeClass(type_id, "emergency")
    vt.setColor(type_id, (255, 0, 0, 255))
    vt.setSpeedFactor(type_id, 1.5)
    vt.setMaxSpeed(type_id, 44.44)
    return type_id


def spawn_emergency_vehicle(api: Any, spec: EmergencyVehicleSpec) -> list[str]:
    """Insert an emergency vehicle on the fastest route (current travel times).

    Returns the list of route edges. Raises ``ValueError`` if no route exists.
    """
    type_id = ensure_emergency_type(api, spec.type_id)
    stage = api.simulation.findRoute(spec.from_edge, spec.to_edge, vType=type_id)
    edges = list(stage.edges)
    if not edges:
        raise ValueError(f"No route from {spec.from_edge} to {spec.to_edge}")
    route_id = f"route_{spec.vehicle_id}"
    api.route.add(route_id, edges)
    api.vehicle.add(spec.vehicle_id, route_id, typeID=type_id, depart=str(spec.depart),
                    departLane=spec.depart_lane, departSpeed=spec.depart_speed)
    return edges


@dataclass
class EmergencyRecord:
    vehicle_id: str
    type_id: str
    depart: float
    route: list[str]
    free_flow_time_s: float
    route_length_m: float
    depart_delay_s: float = 0.0        # insertion delay (scheduled -> actual departure)
    arrival: Optional[float] = None
    mission_time_s: Optional[float] = None  # arrival - scheduled departure (includes insertion delay)
    travel_time_s: Optional[float] = None
    delay_s: Optional[float] = None
    time_loss_s: float = 0.0
    waiting_time_s: float = 0.0
    stops: int = 0
    _halted: bool = field(default=False, repr=False)
    trace: list[tuple] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_") and k not in ("trace", "route")} | {
            "route_edges": len(self.route)}


class EmergencyTracker:
    def __init__(self, api: Any, type_ids: Iterable[str] = (), geo: bool = True,
                 halting_speed: float = 0.1, keep_trace: bool = True):
        self.api = api
        self.type_ids = set(type_ids)
        self.geo = geo
        self.halting_speed = halting_speed
        self.keep_trace = keep_trace
        self.active: dict[str, EmergencyRecord] = {}
        self.completed: list[EmergencyRecord] = []

    def is_emergency(self, vclass: Optional[str], type_id: Optional[str]) -> bool:
        return vclass == "emergency" or (type_id in self.type_ids)

    def _free_flow(self, vid: str, route: list[str]) -> tuple[float, float]:
        """Ideal time and length of the route, INCLUDING the internal lanes crossing each
        junction (they add ~10 % to the length on LuST urban routes)."""
        lane, edge = self.api.lane, self.api.edge
        sf = self.api.vehicle.getSpeedFactor(vid)
        vmax = self.api.vehicle.getMaxSpeed(vid)
        pairs = []
        for i, e in enumerate(route):
            pairs.append((lane.getLength(f"{e}_0"), lane.getMaxSpeed(f"{e}_0") * sf))
            if i + 1 < len(route):
                nxt = route[i + 1]
                via = None
                for k in range(edge.getLaneNumber(e)):
                    # extended link tuple: (lane, prio, open, foe, internal lane, state, dir, length)
                    for link in lane.getLinks(f"{e}_{k}"):  # TraCI default extended=True; libsumo idem
                        if link[0].rsplit("_", 1)[0] == nxt and link[4]:
                            via = (link[4], link[7])
                            break
                    if via:
                        break
                if via:  # junction crossing: link length at the internal lane speed
                    pairs.append((via[1], lane.getMaxSpeed(via[0]) * sf))
        return m.free_flow_time(pairs, vmax), sum(p[0] for p in pairs)

    def on_departed(self, vid: str, type_id: str, time: float) -> None:
        route = list(self.api.vehicle.getRoute(vid))
        ff, length = self._free_flow(vid, route)
        self.active[vid] = EmergencyRecord(vid, type_id, time, route, ff, length,
                                           depart_delay_s=self.api.vehicle.getDepartDelay(vid))

    def update(self, latest: dict[str, dict], time: float, dt: float) -> None:
        for vid, rec in self.active.items():
            v = latest.get(vid)
            if v is None:
                continue
            halted = v["speed"] < self.halting_speed
            if halted and not rec._halted:
                rec.stops += 1
            rec._halted = halted
            if v["waiting_time"] > 0:
                rec.waiting_time_s += dt
            rec.time_loss_s = v.get("time_loss", rec.time_loss_s)
            if self.keep_trace:  # few vehicles -> direct getter is fine
                x, y = self.api.vehicle.getPosition(vid)
                rec.trace.append((time, x, y, v["edge_id"], v["speed"]))

    def on_arrived(self, vid: str, time: float) -> Optional[EmergencyRecord]:
        rec = self.active.pop(vid, None)
        if rec is None:
            return None
        rec.arrival = time
        rec.travel_time_s = time - rec.depart
        rec.delay_s = rec.travel_time_s - rec.free_flow_time_s
        rec.mission_time_s = rec.travel_time_s + rec.depart_delay_s
        self.completed.append(rec)
        return rec

    def snapshot(self, now: float, latest: dict[str, dict]) -> tuple[dict, list[dict]]:
        rows = []
        for vid, rec in self.active.items():
            v = latest.get(vid)
            if v is None:
                continue
            x, y = v["position"]
            lon, lat = self.api.simulation.convertGeo(x, y) if self.geo else (None, None)
            nxt = self.api.vehicle.getNextTLS(vid)
            tls_id, _, tls_dist, tls_state = nxt[0] if nxt else (None, None, None, None)
            rows.append({
                "time": now, "emergency_vehicle_id": vid, "vehicle_type": rec.type_id,
                "x": x, "y": y, "lon": lon, "lat": lat,
                "edge_id": v["edge_id"], "lane_id": v["lane_id"],
                "speed_kmh": m.kmh(v["speed"]), "waiting_time_s": v["waiting_time"],
                "departure": rec.depart, "elapsed_s": now - rec.depart,
                "free_flow_time_s": rec.free_flow_time_s, "route_length_m": rec.route_length_m,
                "distance_m": v["distance"], "progress": (v["distance"] / rec.route_length_m) if rec.route_length_m else None,
                "time_loss_s": v["time_loss"], "stops": rec.stops,
                "next_tls_id": tls_id, "next_tls_distance_m": tls_dist, "next_tls_state": tls_state,
            })
        done = self.completed
        summary = {
            "active": len(rows),
            "completed": len(done),
            "average_travel_time_s": m.safe_mean(r.travel_time_s for r in done),
            "average_delay_s": m.safe_mean(r.delay_s for r in done),
            "average_time_loss_s": m.safe_mean(r.time_loss_s for r in done),
            "vehicles": rows,
            "completed_missions": [r.to_dict() for r in done],
        }
        return summary, rows
