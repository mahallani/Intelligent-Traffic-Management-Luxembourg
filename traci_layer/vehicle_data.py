"""
Vehicle-level data (BO1, BO2, BO3, BO5 and input of BO4/BO6).

Collection strategy (see readers.py for the measurements)
---------------------------------------------------------
LuST has up to ~5 000 simultaneous vehicles at the morning peak. Calling 15 getters per
vehicle per step over TraCI would mean ~75 000 socket round-trips per step. Instead:

* ``STEP_VARS`` (10 values) are read for ALL vehicles at every step with one persistent
  context subscription (or libsumo getters) - only what must be integrated over time;
* ``SNAPSHOT_VARS`` (position, lane, acceleration...) are read in bulk only when an
  observation is built (:meth:`VehicleTracker.enrich`).

Raw values (directly available via TraCI ``vehicle`` domain)
------------------------------------------------------------
=====================  ==============================  ======
field                  TraCI                           unit
=====================  ==============================  ======
x, y                   getPosition                     m (network coords)
edge_id                getRoadID                       -
lane_id                getLaneID                       -
lane_position          getLanePosition                 m
speed                  getSpeed                        m/s
acceleration           getAcceleration                 m/s²
waiting_time           getWaitingTime                  s (resets when the vehicle moves)
accumulated_waiting    getAccumulatedWaitingTime       s (over the last 100 s only!)
time_loss              getTimeLoss                     s (since departure)
distance               getDistance                     m (odometer)
co2/co/hc/pmx/nox      get<X>Emission                  mg/s (last step)
fuel                   getFuelConsumption              mg/s (last step)
=====================  ==============================  ======

Derived values (Cette métrique doit être calculée)
--------------------------------------------------
* ``travel_time``         = arrival time - departure time (both observed via simulation lists)
* ``route_length``        = sum(speed * dt). ``getDistance`` (odometer) is NOT used for trips:
  it was observed to become negative for some LuST vehicles (route changed by the
  rerouting device / state reload). It is still exported per vehicle as ``distance_m``.
* ``total_waiting_time``  = sum of dt over steps where ``getWaitingTime() > 0``
  (``getAccumulatedWaitingTime`` is limited to ``--waiting-time-memory`` = 100 s by default)
* cumulated emissions     = sum of (rate mg/s * dt)
* edge throughput         = number of vehicles leaving an edge (from road-ID changes)
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import traci.constants as tc

from . import metrics as m

if TYPE_CHECKING:
    from .readers import BulkReader

#: Variables read at EVERY step ("standard" preset): what must be integrated over time.
STEP_VARS: dict[str, int] = {
    "speed": tc.VAR_SPEED,
    "waiting_time": tc.VAR_WAITING_TIME,
    "edge_id": tc.VAR_ROAD_ID,
    "time_loss": tc.VAR_TIMELOSS,
    "co2": tc.VAR_CO2EMISSION,
    "co": tc.VAR_COEMISSION,
    "hc": tc.VAR_HCEMISSION,
    "pmx": tc.VAR_PMXEMISSION,
    "nox": tc.VAR_NOXEMISSION,
    "fuel": tc.VAR_FUELCONSUMPTION,
}
#: "light" preset (TraCI ~30 % faster): CO/HC/PMx are then not integrated and the
#: time loss of completed trips comes from the last snapshot only.
STEP_VARS_LIGHT: dict[str, int] = {k: STEP_VARS[k] for k in ("speed", "waiting_time", "edge_id", "co2", "nox", "fuel")}
#: Variables read only when an observation is built.
SNAPSHOT_VARS: dict[str, int] = {
    "position": tc.VAR_POSITION,
    "lane_id": tc.VAR_LANE_ID,
    "lane_position": tc.VAR_LANEPOSITION,
    "acceleration": tc.VAR_ACCELERATION,
    "accumulated_waiting_time": tc.VAR_ACCUMULATED_WAITING_TIME,
    "time_loss": tc.VAR_TIMELOSS,
    "distance": tc.VAR_DISTANCE,
}
#: All vehicle variables collected by the layer (documentation / tests).
VEHICLE_VARS: dict[str, int] = {**STEP_VARS, **SNAPSHOT_VARS}
#: Extra per-step variable for buses only (stop state bit field).
BUS_EXTRA_VARS: dict[str, int] = {"stop_state": tc.VAR_STOPSTATE}

_CODE_TO_NAME = {code: name for name, code in {**VEHICLE_VARS, **BUS_EXTRA_VARS}.items()}
POLLUTANTS = ("co2", "co", "hc", "pmx", "nox", "fuel")


def decode(values: dict[int, Any]) -> dict[str, Any]:
    """{var_code: value} -> {readable_name: value}."""
    return {_CODE_TO_NAME[k]: v for k, v in values.items() if k in _CODE_TO_NAME}


@dataclass
class VehicleTypeInfo:
    """Static vehicle-type information (``vehicletype`` domain, read once per type)."""

    type_id: str
    vclass: str
    length: float
    min_gap: float
    max_speed: float
    emission_class: str


@dataclass
class TripRecord:
    """One vehicle trip. Becomes a completed trip when the vehicle arrives."""

    vehicle_id: str
    type_id: str
    vclass: str
    depart: float                      # observed insertion time (s)
    depart_delay: float = 0.0          # vehicle.getDepartDelay (s) - insertion backlog
    arrival: Optional[float] = None
    travel_time: Optional[float] = None
    route_length: float = 0.0          # distance driven while observed = sum(speed * dt) (m)
    observed_from_departure: bool = True  # False for vehicles already running at collector start
    time_loss_at_start: float = 0.0    # SUMO time loss when the collector started (pre-existing vehicles)
    waiting_time: float = 0.0          # our integration (s)
    time_loss: float = 0.0             # vehicle.getTimeLoss (s)
    teleported: bool = False
    co2_mg: float = 0.0
    co_mg: float = 0.0
    hc_mg: float = 0.0
    pmx_mg: float = 0.0
    nox_mg: float = 0.0
    fuel_mg: float = 0.0
    last_edge: Optional[str] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("last_edge", None)
        return d


class VehicleTracker:
    """Reads the per-step vehicle stream, integrates quantities and records trips."""

    def __init__(self, api: Any, reader: "BulkReader", halting_speed: float = 0.1, light: bool = False):
        self.api = api
        self.reader = reader
        self.halting_speed = halting_speed
        self.step_vars = STEP_VARS_LIGHT if light else STEP_VARS
        self.types: dict[str, VehicleTypeInfo] = {}
        self.active: dict[str, TripRecord] = {}
        self.completed: list[TripRecord] = []
        self.latest: dict[str, dict] = {}          # vehicle_id -> decoded values of the last step
        self.bus_ids: set[str] = set()
        self.edge_exits: Counter = Counter()        # since last reset (throughput)
        self.vehicle_meters: float = 0.0            # VKT accumulator (m)
        self.rate_by_class: dict[str, list[float]] = {}  # emission rates (mg/s) of the last step, POLLUTANTS order
        self._snapshot_time: Optional[float] = None
        reader.start_vehicle_stream(self.step_vars.values())

    # ------------------------------------------------------------------ helpers
    def type_info(self, type_id: str) -> VehicleTypeInfo:
        info = self.types.get(type_id)
        if info is None:
            vt = self.api.vehicletype
            info = VehicleTypeInfo(
                type_id=type_id,
                vclass=vt.getVehicleClass(type_id),
                length=vt.getLength(type_id),
                min_gap=vt.getMinGap(type_id),
                max_speed=vt.getMaxSpeed(type_id),
                emission_class=vt.getEmissionClass(type_id),
            )
            self.types[type_id] = info
        return info

    def vclass_of(self, vehicle_id: str) -> Optional[str]:
        rec = self.active.get(vehicle_id)
        return rec.vclass if rec else None

    # ------------------------------------------------------------- per step
    def on_departed(self, vehicle_ids, time: float) -> list[str]:
        """Register new vehicles (3 TraCI calls each; buses also get a stop-state subscription)."""
        veh = self.api.vehicle
        for vid in vehicle_ids:
            type_id = veh.getTypeID(vid)
            self.type_info(type_id)
            # read per vehicle: setVehicleClass() can override the type's vClass
            vclass = veh.getVehicleClass(vid)
            self.active[vid] = TripRecord(vehicle_id=vid, type_id=type_id, vclass=vclass, depart=time,
                                          depart_delay=veh.getDepartDelay(vid))
            if vclass == "bus":
                self.bus_ids.add(vid)
                if not self.reader.libsumo:
                    veh.subscribe(vid, list(BUS_EXTRA_VARS.values()))
        return list(vehicle_ids)

    def on_teleport(self, vehicle_ids) -> None:
        for vid in vehicle_ids:
            if vid in self.active:
                self.active[vid].teleported = True

    def on_arrived(self, vehicle_ids, time: float) -> list[TripRecord]:
        """Close the trips of arrived vehicles (values of the previous step are kept)."""
        done = []
        for vid in vehicle_ids:
            rec = self.active.pop(vid, None)
            self.latest.pop(vid, None)
            self.bus_ids.discard(vid)
            if rec is None:
                continue  # departed before the collector started
            rec.arrival = time
            rec.travel_time = time - rec.depart
            self.completed.append(rec)
            done.append(rec)
        return done

    def update(self, dt: float) -> dict[str, dict]:
        """Read the vehicle stream (1 TraCI call) and integrate quantities over ``dt``."""
        latest = {vid: decode(vals) for vid, vals in self.reader.read_vehicle_stream().items()}
        if self.bus_ids:
            if self.reader.libsumo:
                for vid in self.bus_ids:
                    if vid in latest:
                        latest[vid]["stop_state"] = self.api.vehicle.getStopState(vid)
            else:
                for vid, vals in self.api.vehicle.getAllSubscriptionResults().items():
                    if vid in latest:
                        latest[vid].update(decode(vals))
        rates = self.rate_by_class = {}
        active = self.active
        vm = 0.0
        for vid, v in latest.items():
            rec = active.get(vid)
            if rec is None:
                continue
            speed = v.get("speed", 0.0)
            if v.get("waiting_time", 0.0) > 0.0:
                rec.waiting_time += dt
            if "time_loss" in v:
                rec.time_loss = v["time_loss"]
            rec.route_length += speed * dt
            vm += speed * dt
            co2, nox, fuel = v.get("co2", 0.0), v.get("nox", 0.0), v.get("fuel", 0.0)
            co, hc, pmx = v.get("co", 0.0), v.get("hc", 0.0), v.get("pmx", 0.0)
            rec.co2_mg += co2 * dt
            rec.nox_mg += nox * dt
            rec.fuel_mg += fuel * dt
            rec.co_mg += co * dt
            rec.hc_mg += hc * dt
            rec.pmx_mg += pmx * dt
            r = rates.get(rec.vclass)
            if r is None:
                r = rates[rec.vclass] = [0.0] * 6
            r[0] += co2; r[1] += co; r[2] += hc; r[3] += pmx; r[4] += nox; r[5] += fuel
            edge = v.get("edge_id", "")
            if edge and edge[0] != ":" and edge != rec.last_edge:
                if rec.last_edge is not None:
                    self.edge_exits[rec.last_edge] += 1
                rec.last_edge = edge
        self.vehicle_meters += vm
        self.latest = latest
        return latest

    def enrich(self, now: float) -> dict[str, dict]:
        """Add the snapshot-only variables (position, lane, ...) to ``latest`` (one bulk read)."""
        if self._snapshot_time != now:
            extra = self.reader.read_once("vehicle", SNAPSHOT_VARS.values())
            for vid, vals in extra.items():
                if vid in self.latest:
                    d = decode(vals)
                    self.latest[vid].update(d)
                    rec = self.active.get(vid)
                    if rec is not None and "time_loss" not in self.step_vars:  # light preset
                        rec.time_loss = d.get("time_loss", rec.time_loss)
            self._snapshot_time = now
        return self.latest

    def pop_edge_exits(self) -> Counter:
        """Return and reset the edge exit counters (used for throughput)."""
        exits, self.edge_exits = self.edge_exits, Counter()
        return exits

    # ------------------------------------------------------------- snapshot
    def summary(self, now: float) -> dict:
        """Aggregated vehicle block of an observation (running vehicles)."""
        vals = list(self.latest.values())
        n = len(vals)
        speeds = [v["speed"] for v in vals]
        halting = sum(1 for s in speeds if s < self.halting_speed)
        by_class: dict[str, dict] = defaultdict(lambda: {"count": 0, "speed_sum": 0.0})
        for vid, v in self.latest.items():
            rec = self.active.get(vid)
            vc = rec.vclass if rec else "unknown"
            by_class[vc]["count"] += 1
            by_class[vc]["speed_sum"] += v["speed"]
        return {
            "count": n,
            "average_speed_kmh": m.kmh(m.safe_mean(speeds)),
            "average_waiting_time_s": m.safe_mean(v["waiting_time"] for v in vals),
            "average_accumulated_waiting_time_s": m.safe_mean(v.get("accumulated_waiting_time") for v in vals),
            "average_time_loss_s": m.safe_mean(v.get("time_loss") for v in vals),
            "halting_count": halting,
            "halting_ratio": halting / n if n else None,
            "total_waiting_time_s": sum(v["waiting_time"] for v in vals),
            "by_class": {
                vc: {"count": d["count"], "average_speed_kmh": m.kmh(d["speed_sum"] / d["count"])}
                for vc, d in sorted(by_class.items())
            },
        }

    def travel_summary(self, since: float = float("-inf")) -> dict:
        """Completed-trip statistics (BO3) for trips arriving strictly after ``since``.

        Travel time and time loss are SUMO's full-trip values (exact even for vehicles that
        departed before the collector started); waiting time is only averaged over trips
        observed from their departure (it is integrated by the collector)."""
        trips = [t for t in self.completed if t.arrival is not None and t.arrival > since]
        full = [t for t in trips if t.observed_from_departure]
        tts = [t.travel_time for t in trips]
        return {
            "completed_trips": len(trips),
            "average_travel_time_s": m.safe_mean(tts),
            "median_travel_time_s": m.percentile(tts, 50),
            "p95_travel_time_s": m.percentile(tts, 95),
            "total_travel_time_s": sum(tts),
            "average_route_length_m": m.safe_mean(t.route_length for t in trips if t.observed_from_departure),
            "completed_trips_observed_from_departure": len(full),
            "average_trip_waiting_time_s": m.safe_mean(t.waiting_time for t in full),
            "average_time_loss_s": m.safe_mean(t.time_loss for t in trips),
            "average_depart_delay_s": m.safe_mean(t.depart_delay for t in trips),
        }

    def details(self, now: float) -> list[dict]:
        """One row per running vehicle (for CSV / DataFrame)."""
        rows = []
        for vid, v in self.latest.items():
            rec = self.active.get(vid)
            x, y = v.get("position", (None, None))
            rows.append({
                "time": now,
                "vehicle_id": vid,
                "vehicle_type": rec.type_id if rec else None,
                "vclass": rec.vclass if rec else None,
                "x": x, "y": y,
                "edge_id": v.get("edge_id"),
                "lane_id": v.get("lane_id"),
                "lane_position_m": v.get("lane_position"),
                "speed_kmh": m.kmh(v.get("speed")),
                "acceleration_ms2": v.get("acceleration"),
                "waiting_time_s": v.get("waiting_time"),
                "accumulated_waiting_time_s": v.get("accumulated_waiting_time"),
                "total_waiting_time_s": rec.waiting_time if rec else None,
                "time_loss_s": v.get("time_loss"),
                "distance_m": v.get("distance"),
                "travel_time_so_far_s": (now - rec.depart) if rec else None,
                "co2_mg_s": v.get("co2"),
                "nox_mg_s": v.get("nox"),
                "fuel_mg_s": v.get("fuel"),
                "co2_cumulated_g": rec.co2_mg * m.MG_TO_G if rec else None,
            })
        return rows
