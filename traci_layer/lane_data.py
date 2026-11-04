"""
Lane-level data - fine congestion analysis at intersections (BO1, BO2).

Raw values - "Disponible directement via l'API TraCI ``lane``":
``getLastStepVehicleNumber`` (veh), ``getLastStepMeanSpeed`` (m/s),
``getLastStepOccupancy`` (fraction 0..1 in SUMO 1.27.1 despite the docstring
saying % - converted to %), ``getLastStepHaltingNumber`` (veh),
``getLastStepLength`` (m), ``getWaitingTime`` (s), ``getLastStepVehicleIDs``.

Queue length (Cette métrique doit être calculée): SUMO only exposes jam lengths on E2
(lane-area) detectors and LuST has none, so the queue of each lane is computed from the
positions/speeds of the vehicles on it (see :func:`metrics.queue_from_vehicles`).

Scope: by default only the ~1 500 lanes controlled by LuST's 201 traffic lights are
monitored ("tls") - that is where queues form and where S1..S4 act. ``"all"`` monitors
the 8 622 lanes of the network (slower).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Union

import traci.constants as tc

from . import metrics as m

LANE_VARS: dict[str, int] = {
    "vehicle_count": tc.LAST_STEP_VEHICLE_NUMBER,
    "mean_speed": tc.LAST_STEP_MEAN_SPEED,
    "occupancy": tc.LAST_STEP_OCCUPANCY,
    "halting_number": tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
    "mean_vehicle_length": tc.LAST_STEP_LENGTH,
    "waiting_time": tc.VAR_WAITING_TIME,
    "vehicle_ids": tc.LAST_STEP_VEHICLE_ID_LIST,
}
_CODE_TO_NAME = {v: k for k, v in LANE_VARS.items()}


def tls_controlled_lanes(api: Any) -> list[str]:
    """Incoming lanes controlled by at least one traffic light."""
    lanes: set[str] = set()
    for tls in api.trafficlight.getIDList():
        lanes.update(api.trafficlight.getControlledLanes(tls))
    return sorted(lanes)


class LaneCollector:
    def __init__(self, api: Any, reader: Any, scope: Union[str, Iterable[str]] = "tls",
                 halting_speed: float = 0.1, thresholds=(0.3, 0.5, 0.75)):
        self.api = api
        self.reader = reader
        self.halting_speed = halting_speed
        self.thresholds = thresholds
        if scope == "tls":
            ids = tls_controlled_lanes(api)
        elif scope == "all":
            ids = [l for l in api.lane.getIDList() if not l.startswith(":")]
        else:
            ids = list(scope)
        self.lane_ids = ids
        self.static = {
            l: {"length": api.lane.getLength(l), "allowed_speed": api.lane.getMaxSpeed(l),
                "edge_id": api.lane.getEdgeID(l)}
            for l in ids
        }
        self.last_queues: dict[str, tuple[int, float]] = {}

    def read(self) -> dict[str, dict]:
        raw = self.reader.read_once("lane", LANE_VARS.values(), self.lane_ids)
        return {l: {_CODE_TO_NAME[k]: v for k, v in vals.items() if k in _CODE_TO_NAME}
                for l, vals in raw.items() if l in self.static}

    def snapshot(self, now: float, vehicle_latest: dict[str, dict],
                 vehicle_length: Optional[callable] = None) -> tuple[dict, list[dict]]:
        """Return (summary, rows). ``vehicle_length(vid)`` gives the length of a vehicle."""
        data = self.read()
        rows, queues = [], {}
        total_q, max_q, max_q_lane, occ_sum, occupied, halting = 0.0, 0.0, None, 0.0, 0, 0
        for l, d in data.items():
            st = self.static[l]
            vehs = []
            for vid in d["vehicle_ids"]:
                v = vehicle_latest.get(vid)
                if v is not None:
                    length = vehicle_length(vid) if vehicle_length else d["mean_vehicle_length"]
                    vehs.append((v["lane_position"], v["speed"], length))
            nq, qlen = m.queue_from_vehicles(st["length"], vehs, self.halting_speed)
            queues[l] = (nq, qlen)
            total_q += qlen
            if qlen > max_q:
                max_q, max_q_lane = qlen, l
            n = int(d["vehicle_count"])
            if n:
                occupied += 1
                occ_sum += (d["occupancy"] * 100.0)
            halting += int(d["halting_number"])
            idx = m.congestion_index(d["mean_speed"], st["allowed_speed"]) if n else 0.0
            rows.append({
                "time": now, "lane_id": l, "edge_id": st["edge_id"], "length_m": st["length"],
                "vehicle_count": n,
                "mean_speed_kmh": m.kmh(d["mean_speed"]) if n else None,
                "occupancy_pct": (d["occupancy"] * 100.0),
                "halting_number": int(d["halting_number"]),
                "waiting_time_s": d["waiting_time"],
                "queue_vehicles": nq, "queue_length_m": qlen,
                "queue_ratio": qlen / st["length"] if st["length"] > 0 else None,  # spill-back risk
                "congestion_index": idx,
            })
        self.last_queues = queues
        summary = {
            "lanes_monitored": len(rows),
            "occupied_lanes": occupied,
            "average_occupancy_pct": occ_sum / occupied if occupied else 0.0,
            "halting_vehicles": halting,
            "queue_length_total_m": total_q,
            "queue_length_max_m": max_q,
            "queue_length_max_lane": max_q_lane,
            "queued_vehicles": sum(q[0] for q in queues.values()),
            "lanes_with_queue": sum(1 for q in queues.values() if q[0] > 0),
            "spillback_lanes": sum(1 for r in rows if r["queue_ratio"] is not None and r["queue_ratio"] >= 0.9),
        }
        return summary, rows
