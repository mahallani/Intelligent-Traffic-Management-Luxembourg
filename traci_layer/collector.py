"""
TrafficDataCollector - the single entry point used by the agents.

    SUMO -> TraCI connection -> TrafficDataCollector -> Observation (dict / JSON)
                                                     -> tables (CSV / DataFrame)
                                                     -> ScenarioKPIs (Decision Agent)

Two rhythms:

* :meth:`step` - called at EVERY simulation step. Light work: departures / arrivals,
  vehicle subscriptions, waiting time & emission integration, bus stop events,
  emergency tracking. Must not be skipped, otherwise travel times and cumulated
  values become wrong.
* :meth:`observe` - called every ``snapshot_interval`` seconds (default 60 s). Builds
  the full structured observation (edges, lanes, traffic lights, buses...).

Example
-------
>>> with SumoConnection(SumoConfig(end=600)) as api:
...     col = TrafficDataCollector(api)
...     for obs in col.run(duration=300, observe_every=60):
...         print(format_observation(obs))
...     kpis = col.kpis()
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from .bus_data import BusTracker
from .config import DEFAULT_SUMOCFG, CollectorConfig, cfg_route_files
from .edge_data import EdgeCollector
from .emergency_data import EmergencyTracker
from .environmental_data import EnvironmentAccumulator
from .kpi import ScenarioKPIs, compute_kpis
from .lane_data import LaneCollector
from .network import NetworkTopology
from .readers import BulkReader
from .simulation import SimulationController
from .traffic_light_data import TrafficLightCollector
from .vehicle_data import VehicleTracker

SCHEMA_VERSION = "1.0"


def clock(t: float) -> str:
    """LuST time (s since 00:00) -> 'HH:MM:SS'."""
    t = int(t)
    return f"{(t // 3600) % 24:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


class TrafficDataCollector:
    def __init__(self, api: Any, config: Optional[CollectorConfig] = None,
                 sumocfg: Optional[Path] = DEFAULT_SUMOCFG, scenario: str = "S0",
                 run_id: Optional[str] = None, topology: Optional[NetworkTopology] = None):
        self.api = api
        self.config = cfg = config or CollectorConfig()
        self.scenario = scenario
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.sim = SimulationController(api)
        self.start_time = self.sim.time
        self.reader = BulkReader(api)
        self.vehicles = VehicleTracker(api, self.reader, cfg.halting_speed, light=cfg.light_step_vars)
        self.env = EnvironmentAccumulator()

        if topology is None and sumocfg is not None and cfg.collect_edges:
            topology = NetworkTopology.from_sumocfg(sumocfg)
        self.topology = topology
        self.edges = EdgeCollector(api, self.reader, thresholds=cfg.congestion_thresholds,
                                   congested_index=cfg.congested_edge_index,
                                   top_n=cfg.top_n_bottlenecks, topology=topology) if cfg.collect_edges else None
        self.lanes = LaneCollector(api, self.reader, cfg.lane_scope, cfg.halting_speed,
                                   cfg.congestion_thresholds) if cfg.lane_scope else None
        self.tls = TrafficLightCollector(api, self.reader, top_n=cfg.top_n_bottlenecks) if cfg.collect_traffic_lights else None

        self.buses = None
        if cfg.collect_buses:
            files = cfg.bus_route_files
            if files is None and sumocfg is not None:
                files = [f for f in cfg_route_files(sumocfg) if "bus" in f.name.lower()]
            self.buses = BusTracker(api, files or [], cfg.bunching_ratio, cfg.geo_positions)
        self.emergency = EmergencyTracker(api, cfg.emergency_type_ids, cfg.geo_positions,
                                          cfg.halting_speed) if cfg.collect_emergency else None

        self.history: list[dict] = []           # observations (summaries)
        self.latest_tables: dict[str, list] = {}  # rows of the LAST observation
        self.tables: dict[str, list] = {}         # accumulated rows (include_details=True)
        self._last_observe: Optional[float] = None
        self._last_trip_count = 0

        # Vehicles already in the network (e.g. after --load-state) are tracked from now on.
        existing = list(api.vehicle.getIDList())
        if existing:
            self._register_departures(existing, self.sim.time, preexisting=True)
        self.vehicles.update(0.0)  # read current values without integrating anything

    # ================================================================= per step
    def _register_departures(self, ids, time: float, preexisting: bool = False) -> None:
        self.vehicles.on_departed(ids, time)
        for vid in ids:
            rec = self.vehicles.active[vid]
            if preexisting:  # real departure happened before the collector started
                rec.depart = self.api.vehicle.getDeparture(vid)
                rec.observed_from_departure = False
                rec.time_loss_at_start = rec.time_loss = self.api.vehicle.getTimeLoss(vid)
            if self.buses is not None and rec.vclass == "bus":
                self.buses.on_departed(vid, rec.depart, preexisting)
            elif self.emergency is not None and self.emergency.is_emergency(rec.vclass, rec.type_id):
                self.emergency.on_departed(vid, rec.type_id, rec.depart)

    def step(self) -> float:
        """Advance SUMO by one step and update all per-step trackers. Returns sim time."""
        ev = self.sim.step()
        t, dt = ev.time, self.sim.step_length
        if ev.departed:
            self._register_departures(ev.departed, t)
        if ev.teleport_started:
            self.vehicles.on_teleport(ev.teleport_started)
        for vid in ev.arrived:
            if self.buses is not None:
                self.buses.on_arrived(vid)
            if self.emergency is not None:
                self.emergency.on_arrived(vid, t)
        self.vehicles.on_arrived(ev.arrived, t)

        latest = self.vehicles.update(dt)
        self.sim.counters.vehicle_seconds += len(latest) * dt
        self.env.update(self.vehicles.rate_by_class, dt)
        if self.buses is not None and self.buses.active:
            self.buses.update(latest, t)
        if self.emergency is not None and self.emergency.active:
            self.emergency.update(latest, t, dt)
        return t

    # ================================================================ snapshot
    def observe(self) -> dict:
        """Build the full structured observation of the current step."""
        cfg = self.config
        now = self.sim.time
        latest = self.vehicles.enrich(now)   # adds position, lane, ... (one bulk read)
        tables: dict[str, list] = {}

        vehicles = self.vehicles.summary(now)
        travel_window = self.vehicles.travel_summary(since=self._last_observe if self._last_observe is not None else float("-inf"))
        travel_total = self.vehicles.travel_summary()
        exits = self.vehicles.pop_edge_exits()

        congestion: dict = {}
        if self.edges is not None:
            edge_summary, edge_rows, _ = self.edges.snapshot(now, exits)
            tables["edges"] = edge_rows
            congestion.update({
                "average_occupancy_pct": edge_summary["average_occupancy_pct"],
                "halting_vehicles": edge_summary["halting_vehicles"],
                "network_congestion_index": edge_summary["network_congestion_index"],
                "level": edge_summary["network_congestion_level"],
                "congested_edges": edge_summary["congested_edges"],
                "queue_length_m": edge_summary["estimated_queue_length_m"],
                "queue_method": "edge_estimate",
                "edges": edge_summary,
            })
        lane_rows = None
        if self.lanes is not None:
            type_len = self.vehicles.types
            active = self.vehicles.active
            lane_summary, lane_rows = self.lanes.snapshot(
                now, latest, lambda vid: type_len[active[vid].type_id].length if vid in active else 5.0)
            tables["lanes"] = lane_rows
            congestion.update({
                "queue_length_m": lane_summary["queue_length_total_m"],
                "queue_method": "tls_lanes_vehicle_positions",
                "max_queue_length_m": lane_summary["queue_length_max_m"],
                "queued_vehicles": lane_summary["queued_vehicles"],
                "tls_lanes": lane_summary,
            })
        if "halting_vehicles" not in congestion:
            congestion["halting_vehicles"] = vehicles["halting_count"]

        tls_summary = None
        if self.tls is not None:
            tls_summary, tls_rows = self.tls.snapshot(now, self.lanes.last_queues if self.lanes else None, lane_rows)
            tables["traffic_lights"] = tls_rows

        bus_summary = None
        if self.buses is not None:
            bus_summary, bus_rows = self.buses.snapshot(now, latest)
            tables["buses"] = bus_rows

        em_summary = None
        if self.emergency is not None:
            em_summary, em_rows = self.emergency.snapshot(now, latest)
            tables["emergency"] = em_rows

        vkm = self.vehicles.vehicle_meters / 1000.0
        obs = {
            "schema_version": SCHEMA_VERSION,
            "meta": {
                "network": "LuST - Luxembourg SUMO Traffic",
                "scenario": self.scenario,
                "run_id": self.run_id,
                "timestamp": now,
                "clock": clock(now),
                "step_length": self.sim.step_length,
                "observed_since": self.start_time,
            },
            "simulation": self.sim.status(vehicles["count"]),
            "vehicles": vehicles,
            "congestion": congestion,
            "travel": {"since_last_observation": travel_window, "cumulative": travel_total,
                       "vehicle_km_travelled": vkm,
                       "vehicle_hours_travelled": self.sim.counters.vehicle_seconds / 3600.0},
            "environment": self.env.summary(vkm),
            "buses": bus_summary,
            "emergency": em_summary,
            "traffic_lights": tls_summary,
        }
        if cfg.include_details:
            tables["vehicles"] = self.vehicles.details(now)
            for name, rows in tables.items():
                self.tables.setdefault(name, []).extend(rows)
        self.latest_tables = tables
        self.history.append(obs)
        self._last_observe = now
        return obs

    # ================================================================== loops
    def run(self, duration: Optional[float] = None, until: Optional[float] = None,
            observe_every: Optional[float] = None, stop_when_empty: bool = True,
            on_step: Optional[Callable[["TrafficDataCollector"], None]] = None) -> Iterator[dict]:
        """Generator: step the simulation and yield an observation every ``observe_every`` s.

        ``on_step`` is called after every step (hook for agents that act in real time,
        e.g. an Intervention Agent applying a strategy).
        """
        every = observe_every or self.config.snapshot_interval
        end = until if until is not None else (self.sim.time + duration if duration is not None else float("inf"))
        next_obs = self.sim.time + every
        while self.sim.time < end:
            if stop_when_empty and not self.sim.has_pending_traffic():
                break
            t = self.step()
            if on_step is not None:
                on_step(self)
            if t + 1e-9 >= next_obs:
                next_obs += every
                yield self.observe()

    def kpis(self) -> ScenarioKPIs:
        """Scenario KPIs over the whole observation window (Decision Agent input)."""
        return compute_kpis(self)

    def trips_table(self) -> list[dict]:
        return [t.to_dict() for t in self.vehicles.completed]
