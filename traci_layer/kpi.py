"""
Scenario-level KPIs - the identical KPI set computed for every strategy S0..S4 and
handed to the Decision Agent (BO6).

All KPIs are computed over the SAME observation window (collector start -> end).
For a fair comparison every scenario must:
  1. start from the same saved state (``SumoConfig(load_state=...)``),
  2. use the same seed, the same incident and the same emergency mission,
  3. run for the same duration.

``KPI_DIRECTIONS`` tells the Decision Agent whether each KPI must be minimised or
maximised; the weighting / scoring function itself belongs to the Decision Agent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from . import metrics as m

#: "min" = lower is better, "max" = higher is better.
KPI_DIRECTIONS: dict[str, str] = {
    # BO1 waiting time
    "total_waiting_time_s": "min",
    "average_waiting_time_per_vehicle_s": "min",
    "average_halting_vehicles": "min",
    # BO2 congestion
    "network_mean_speed_kmh": "max",
    "average_congestion_index": "min",
    "average_congested_edges": "min",
    "average_total_queue_length_m": "min",
    "max_lane_queue_length_m": "min",
    "teleports": "min",
    "pending_vehicles_end": "min",
    # BO3 travel time
    "completed_trips": "max",
    "average_travel_time_s": "min",
    "total_time_loss_in_window_s": "min",
    "vehicle_hours_travelled": "min",
    # BO4 emergency
    "emergency_average_travel_time_s": "min",
    "emergency_average_delay_s": "min",
    # BO5 environment
    "co2_kg": "min",
    "nox_g": "min",
    "fuel_kg": "min",
    "pmx_g": "min",
    # public transport
    "bus_average_delay_s": "min",
    "bus_bunching_events": "min",
    "bus_headway_cv": "min",
}


@dataclass
class ScenarioKPIs:
    scenario: str
    run_id: str
    start_time: float
    end_time: float
    duration_s: float
    # BO1
    total_waiting_time_s: float = 0.0
    average_waiting_time_per_vehicle_s: Optional[float] = None
    average_halting_vehicles: Optional[float] = None
    max_halting_vehicles: Optional[int] = None
    # BO2
    network_mean_speed_kmh: Optional[float] = None
    average_congestion_index: Optional[float] = None
    average_congested_edges: Optional[float] = None
    max_congested_edges: Optional[int] = None
    average_total_queue_length_m: Optional[float] = None   # sum of all TLS-lane queues, time-averaged
    max_lane_queue_length_m: Optional[float] = None        # longest single-lane queue seen
    teleports: int = 0
    pending_vehicles_end: int = 0
    # BO3
    vehicles_observed: int = 0
    completed_trips: int = 0
    completed_trips_observed_from_departure: int = 0
    average_travel_time_s: Optional[float] = None          # trips observed from departure only
    average_travel_time_all_completed_s: Optional[float] = None
    total_travel_time_s: float = 0.0
    average_time_loss_s: Optional[float] = None            # trips observed from departure only
    total_time_loss_in_window_s: float = 0.0               # time loss accrued during the window, all vehicles
    vehicle_hours_travelled: float = 0.0
    vehicle_km_travelled: float = 0.0
    # BO4
    emergency_missions: int = 0
    emergency_completed: int = 0
    emergency_average_travel_time_s: Optional[float] = None
    emergency_average_delay_s: Optional[float] = None
    emergency_details: list = field(default_factory=list)
    # BO5
    co2_kg: float = 0.0
    nox_g: float = 0.0
    fuel_kg: float = 0.0
    co_g: Optional[float] = None    # None when light_step_vars=True (not integrated)
    hc_g: Optional[float] = None
    pmx_g: Optional[float] = None
    co2_g_per_km: Optional[float] = None
    # public transport
    bus_trips_observed: int = 0
    bus_average_delay_s: Optional[float] = None
    bus_average_dwell_s: Optional[float] = None
    bus_bunching_events: int = 0
    bus_headway_cv: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def comparable(self) -> dict:
        """Only the KPIs listed in ``KPI_DIRECTIONS`` (input of the Decision Agent)."""
        d = self.to_dict()
        return {k: d.get(k) for k in KPI_DIRECTIONS}


def _avg(history: list[dict], *path: str) -> Optional[float]:
    vals = []
    for obs in history:
        cur = obs
        for p in path:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is not None:
            vals.append(cur)
    return m.safe_mean(vals)


def _max(history: list[dict], *path: str):
    vals = []
    for obs in history:
        cur = obs
        for p in path:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is not None:
            vals.append(cur)
    return max(vals) if vals else None


def compute_kpis(collector) -> ScenarioKPIs:
    """Build the :class:`ScenarioKPIs` of a finished (or running) collection."""
    c = collector
    now = c.sim.time
    veh = c.vehicles
    trips = veh.completed
    running = list(veh.active.values())
    every = trips + running
    k = ScenarioKPIs(scenario=c.scenario, run_id=c.run_id, start_time=c.start_time,
                     end_time=now, duration_s=now - c.start_time)
    hist = c.history

    # BO1 - waiting (trips + vehicles still running, only time observed by the collector)
    k.total_waiting_time_s = sum(t.waiting_time for t in every)
    k.average_waiting_time_per_vehicle_s = (k.total_waiting_time_s / len(every)) if every else None
    k.average_halting_vehicles = _avg(hist, "vehicles", "halting_count")
    k.max_halting_vehicles = _max(hist, "vehicles", "halting_count")

    # BO2 - congestion
    vht_s = c.sim.counters.vehicle_seconds
    k.vehicle_hours_travelled = vht_s / 3600.0
    k.vehicle_km_travelled = veh.vehicle_meters / 1000.0
    k.network_mean_speed_kmh = (veh.vehicle_meters / vht_s * 3.6) if vht_s > 0 else None  # space-mean speed
    k.average_congestion_index = _avg(hist, "congestion", "network_congestion_index")
    k.average_congested_edges = _avg(hist, "congestion", "congested_edges")
    k.max_congested_edges = _max(hist, "congestion", "congested_edges")
    # queue KPIs only from the lane method (None if lane collection is disabled) so that
    # runs made with different settings are never silently compared
    k.average_total_queue_length_m = _avg(hist, "congestion", "tls_lanes", "queue_length_total_m")
    k.max_lane_queue_length_m = _max(hist, "congestion", "tls_lanes", "queue_length_max_m")
    k.teleports = c.sim.counters.teleports
    k.pending_vehicles_end = len(c.api.simulation.getPendingVehicles())

    # BO3 - travel time
    # Window-consistent definitions: trips that departed before the collector started
    # carry history that is identical in every scenario and would dilute differences.
    k.vehicles_observed = len(every)
    k.completed_trips = len(trips)
    full = [t for t in trips if t.observed_from_departure]
    k.completed_trips_observed_from_departure = len(full)
    k.average_travel_time_s = m.safe_mean(t.travel_time for t in full)
    k.average_travel_time_all_completed_s = m.safe_mean(t.travel_time for t in trips)
    k.total_travel_time_s = sum(t.travel_time for t in trips)
    k.average_time_loss_s = m.safe_mean(t.time_loss for t in full)
    k.total_time_loss_in_window_s = sum(t.time_loss - t.time_loss_at_start for t in every)

    # BO4 - emergency
    if c.emergency is not None:
        em = c.emergency
        k.emergency_missions = len(em.completed) + len(em.active)
        k.emergency_completed = len(em.completed)
        k.emergency_average_travel_time_s = m.safe_mean(r.travel_time_s for r in em.completed)
        k.emergency_average_delay_s = m.safe_mean(r.delay_s for r in em.completed)
        k.emergency_details = [r.to_dict() for r in em.completed] + [
            {**r.to_dict(), "unfinished": True, "elapsed_s": now - r.depart} for r in em.active.values()]

    # BO5 - environment
    cm = c.env.cumulated_mg
    k.co2_kg = cm["co2"] * m.MG_TO_KG
    k.nox_g = cm["nox"] * m.MG_TO_G
    k.fuel_kg = cm["fuel"] * m.MG_TO_KG
    if "pmx" in c.vehicles.step_vars:
        k.co_g = cm["co"] * m.MG_TO_G
        k.hc_g = cm["hc"] * m.MG_TO_G
        k.pmx_g = cm["pmx"] * m.MG_TO_G
    k.co2_g_per_km = (cm["co2"] * m.MG_TO_G / k.vehicle_km_travelled) if k.vehicle_km_travelled > 0 else None

    # public transport
    buses = [t for t in every if t.vclass == "bus"]
    k.bus_trips_observed = len(buses)
    k.bus_average_delay_s = m.safe_mean(t.time_loss for t in buses)
    if c.buses is not None:
        ev = c.buses.events
        k.bus_average_dwell_s = m.safe_mean(e.dwell for e in ev if e.dwell is not None)
        k.bus_bunching_events = sum(1 for e in ev if e.bunched)
        k.bus_headway_cv = m.coefficient_of_variation([e.headway for e in ev if e.headway is not None])
    return k


def compare_scenarios(results: dict[str, ScenarioKPIs]):
    """Side-by-side table (pandas DataFrame) of the comparable KPIs of several scenarios."""
    import pandas as pd

    df = pd.DataFrame({name: k.comparable() for name, k in results.items()})
    df.insert(0, "direction", [KPI_DIRECTIONS[i] for i in df.index])
    return df
