"""
Edge (road segment) data - congestion, bottlenecks, propagation (BO2, BO3, BO5).

Raw values - "Disponible directement via l'API TraCI ``edge``" (read in bulk at each
snapshot, see readers.py):

=========================  =====================================  =========
field                      TraCI                                  unit
=========================  =====================================  =========
vehicle_count              edge.getLastStepVehicleNumber          veh
mean_speed                 edge.getLastStepMeanSpeed              m/s *
occupancy                  edge.getLastStepOccupancy              0..1 (*)
halting_number             edge.getLastStepHaltingNumber          veh (speed < 0.1 m/s)
mean_vehicle_length        edge.getLastStepLength                 m
travel_time                edge.getTraveltime                     s (length / mean speed)
waiting_time               edge.getWaitingTime                    s (sum over vehicles)
co2 / nox / fuel           edge.getCO2Emission ...                mg/s
=========================  =====================================  =========

(*) The TraCI docstring says "%" but SUMO 1.27.1 returns a FRACTION (verified on LuST:
value == sum(vehicle lengths) / lane length). We multiply by 100 -> ``occupancy_pct``.

\\* On an EMPTY edge SUMO returns the allowed speed as mean speed -> empty edges are
excluded from congestion statistics.

Derived (Cette métrique doit être calculée): congestion index & level, estimated queue,
throughput (veh/h, from vehicles leaving the edge), congested edge set, propagation.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

import traci.constants as tc

from . import metrics as m

EDGE_VARS: dict[str, int] = {
    "vehicle_count": tc.LAST_STEP_VEHICLE_NUMBER,
    "mean_speed": tc.LAST_STEP_MEAN_SPEED,
    "occupancy": tc.LAST_STEP_OCCUPANCY,
    "halting_number": tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
    "mean_vehicle_length": tc.LAST_STEP_LENGTH,
    "travel_time": tc.VAR_CURRENT_TRAVELTIME,
    "waiting_time": tc.VAR_WAITING_TIME,
    "co2": tc.VAR_CO2EMISSION,
    "nox": tc.VAR_NOXEMISSION,
    "fuel": tc.VAR_FUELCONSUMPTION,
}
_CODE_TO_NAME = {v: k for k, v in EDGE_VARS.items()}


class EdgeCollector:
    """Collects and aggregates edge data of the whole LuST network (5 779 edges)."""

    def __init__(self, api: Any, reader: Any, edge_ids: Optional[list[str]] = None,
                 thresholds=(0.3, 0.5, 0.75), congested_index: float = 0.5,
                 top_n: int = 10, topology: Any = None):
        self.api = api
        self.reader = reader
        self.thresholds = thresholds
        self.congested_index = congested_index
        self.top_n = top_n
        self.topology = topology
        ids = edge_ids if edge_ids is not None else api.edge.getIDList()
        self.edge_ids = [e for e in ids if not e.startswith(":")]  # skip internal junction edges
        self.static: dict[str, dict] = {}
        self.previous_congested: set[str] = set()
        self.last_snapshot_time: Optional[float] = None
        self._load_static()

    def _load_static(self) -> None:
        edge, lane = self.api.edge, self.api.lane
        for e in self.edge_ids:
            n = edge.getLaneNumber(e)
            first = f"{e}_0"
            self.static[e] = {
                "lanes": n,
                "length": lane.getLength(first),
                "allowed_speed": max(lane.getMaxSpeed(f"{e}_{i}") for i in range(n)),
                "street_name": edge.getStreetName(e),
            }

    def read(self) -> dict[str, dict]:
        """Current values of all monitored edges (one bulk read, see readers.py)."""
        raw = self.reader.read_once("edge", EDGE_VARS.values(), self.edge_ids)
        return {e: {_CODE_TO_NAME[k]: v for k, v in vals.items() if k in _CODE_TO_NAME}
                for e, vals in raw.items() if e in self.static}

    # ----------------------------------------------------------------- snapshot
    def snapshot(self, now: float, edge_exits: Counter) -> tuple[dict, list[dict], set[str]]:
        """Return (congestion summary, per-edge rows, congested edge set)."""
        data = self.read()
        interval = (now - self.last_snapshot_time) if self.last_snapshot_time is not None else None
        self.last_snapshot_time = now

        rows: list[dict] = []
        congested: set[str] = set()
        occupied = 0
        occ_sum = 0.0
        weighted_idx = 0.0
        veh_total = 0
        halting_total = 0
        queue_est_total = 0.0
        waiting_total = 0.0
        for e, d in data.items():
            st = self.static[e]
            n = int(d["vehicle_count"])
            if n > 0:
                idx = m.congestion_index(d["mean_speed"], st["allowed_speed"])
                occupied += 1
                occ_sum += (d["occupancy"] * 100.0)
                weighted_idx += idx * n
                veh_total += n
                if idx >= self.congested_index:
                    congested.add(e)
            else:
                idx = 0.0
            halting = int(d["halting_number"])
            halting_total += halting
            q_est = m.estimated_queue_length(halting, d["mean_vehicle_length"])
            queue_est_total += q_est
            waiting_total += d["waiting_time"]
            exits = edge_exits.get(e, 0)
            rows.append({
                "time": now,
                "edge_id": e,
                "street_name": st["street_name"],
                "lanes": st["lanes"],
                "length_m": st["length"],
                "allowed_speed_kmh": m.kmh(st["allowed_speed"]),
                "vehicle_count": n,
                "mean_speed_kmh": m.kmh(d["mean_speed"]) if n else None,
                "occupancy_pct": (d["occupancy"] * 100.0),
                "halting_number": halting,
                "waiting_time_s": d["waiting_time"],
                "travel_time_s": d["travel_time"],
                "estimated_queue_m": q_est,
                "throughput_veh_h": (exits * 3600.0 / interval) if interval else None,
                "congestion_index": idx,
                "congestion_level": m.congestion_level(idx if n else None, self.thresholds) if n else "empty",
                "co2_mg_s": d["co2"],
                "nox_mg_s": d["nox"],
                "fuel_mg_s": d["fuel"],
            })

        net_idx = weighted_idx / veh_total if veh_total else 0.0
        newly = congested - self.previous_congested
        recovered = self.previous_congested - congested
        propagated = self._propagated(newly, self.previous_congested)
        self.previous_congested = congested

        bottlenecks = sorted(
            (r for r in rows if r["vehicle_count"] > 0),
            key=lambda r: (r["halting_number"], r["congestion_index"]), reverse=True,
        )[: self.top_n]
        summary = {
            "edges_monitored": len(rows),
            "occupied_edges": occupied,
            "average_occupancy_pct": (occ_sum / occupied) if occupied else 0.0,
            "max_occupancy_pct": max((r["occupancy_pct"] for r in rows), default=0.0),
            "halting_vehicles": halting_total,
            "waiting_time_on_edges_s": waiting_total,
            "estimated_queue_length_m": queue_est_total,
            "network_congestion_index": net_idx,
            "network_congestion_level": m.congestion_level(net_idx, self.thresholds),
            "congested_edges": len(congested),
            "congested_edge_share": (len(congested) / occupied) if occupied else 0.0,
            "newly_congested_edges": len(newly),
            "recovered_edges": len(recovered),
            "propagated_congestion_edges": len(propagated) if propagated is not None else None,
            "top_bottlenecks": [
                {k: r[k] for k in ("edge_id", "street_name", "vehicle_count", "halting_number",
                                   "mean_speed_kmh", "occupancy_pct", "congestion_index", "estimated_queue_m")}
                for r in bottlenecks
            ],
            "congested_edge_ids": sorted(congested),
        }
        return summary, rows, congested

    def _propagated(self, newly: set[str], previous: set[str]) -> Optional[set[str]]:
        """Newly congested edges that are directly UPSTREAM of an edge already congested.

        Congestion spreads backwards (spillback), so a new congested edge feeding a
        previously congested one is counted as propagation. Needs the network topology.
        """
        if self.topology is None:
            return None
        return {e for e in newly if any(d in previous for d in self.topology.downstream(e))}
