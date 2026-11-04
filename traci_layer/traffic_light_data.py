"""
Traffic-light data (input for S1 Bus Priority, S2 Emergency Priority, S3 Optimisation).

LuST facts (verified on lust.net.xml with SUMO 1.27.1):
* 201 traffic-light programs (203 ``traffic_light`` junctions, some share one program)
* all are declared ``type="actuated"``, programID ``"0"``,
* BUT no phase defines ``minDur`` / ``maxDur``, so SUMO uses minDur = maxDur = duration:
  in practice they behave as FIXED-TIME plans (``getAllProgramLogics`` confirms it).
* ``tll.static.xml`` (not loaded by dua.actuated.sumocfg) contains alternative static
  programs with programID ``"1"``.

Raw values - "Disponible directement via l'API TraCI ``trafficlight``":

====================  =================================  ============
field                 TraCI                              unit
====================  =================================  ============
state                 getRedYellowGreenState             string rRgGyYoO per link
phase                 getPhase                           index
program               getProgram                         programID
phase_duration        getPhaseDuration                   s
next_switch           getNextSwitch                      s (absolute sim time)
spent                 getSpentDuration                   s
programs / phases     getAllProgramLogics                Logic objects
controlled lanes      getControlledLanes                 lane ids
controlled links      getControlledLinks                 (in, out, via) per link index
====================  =================================  ============

Derived (calculated): remaining time = next_switch - now, cycle time, queue and halting
vehicles on the controlled lanes, number of green links.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

import traci.constants as tc

TLS_VARS: dict[str, int] = {
    "state": tc.TL_RED_YELLOW_GREEN_STATE,
    "phase": tc.TL_CURRENT_PHASE,
    "program": tc.TL_CURRENT_PROGRAM,
    "phase_duration": tc.TL_PHASE_DURATION,
    "next_switch": tc.TL_NEXT_SWITCH,
    "spent": tc.TL_SPENT_DURATION,
}
_CODE_TO_NAME = {v: k for k, v in TLS_VARS.items()}

_TYPE_NAMES = {0: "static", 3: "actuated", 4: "NEMA", 5: "delay_based"}


class TrafficLightCollector:
    def __init__(self, api: Any, reader: Any, tls_ids: Optional[list[str]] = None, top_n: int = 10):
        self.api = api
        self.reader = reader
        self.top_n = top_n
        tl = api.trafficlight
        self.tls_ids = list(tls_ids) if tls_ids is not None else list(tl.getIDList())
        self.static: dict[str, dict] = {}
        for t in self.tls_ids:
            logics = tl.getAllProgramLogics(t)
            programs = {}
            for lg in logics:
                phases = lg.phases
                programs[lg.programID] = {
                    "type": _TYPE_NAMES.get(lg.type, str(lg.type)),
                    "phases": len(phases),
                    "cycle_time_s": sum(p.duration for p in phases),
                    "effectively_fixed": all(p.minDur == p.maxDur for p in phases),
                }
            lanes = list(dict.fromkeys(tl.getControlledLanes(t)))
            self.static[t] = {
                "programs": programs,
                "controlled_lanes": lanes,
                "controlled_links": len(tl.getControlledLinks(t)),
            }

    def read(self) -> dict[str, dict]:
        raw = self.reader.read_once("trafficlight", TLS_VARS.values(), self.tls_ids)
        return {t: {_CODE_TO_NAME[k]: v for k, v in vals.items() if k in _CODE_TO_NAME}
                for t, vals in raw.items() if t in self.static}

    def snapshot(self, now: float, lane_queues: Optional[dict[str, tuple[int, float]]] = None,
                 lane_rows: Optional[list[dict]] = None) -> tuple[dict, list[dict]]:
        data = self.read()
        halting_by_lane = {r["lane_id"]: r["halting_number"] for r in (lane_rows or [])}
        rows = []
        for t, d in data.items():
            st = self.static[t]
            lanes = st["controlled_lanes"]
            q = [lane_queues.get(l, (0, 0.0)) for l in lanes] if lane_queues else []
            prog = st["programs"].get(d["program"], {})
            rows.append({
                "time": now,
                "tls_id": t,
                "program": d["program"],
                "program_type": prog.get("type"),
                "phase": d["phase"],
                "state": d["state"],
                "green_links": sum(1 for c in d["state"] if c in "Gg"),
                "phase_duration_s": d["phase_duration"],
                "spent_s": d["spent"],
                "remaining_s": d["next_switch"] - now,
                "cycle_time_s": prog.get("cycle_time_s"),
                "controlled_lanes": len(lanes),
                "controlled_links": st["controlled_links"],
                "queued_vehicles": sum(x[0] for x in q) if q else None,
                "queue_length_m": sum(x[1] for x in q) if q else None,
                "halting_vehicles": sum(halting_by_lane.get(l, 0) for l in lanes) if halting_by_lane else None,
            })
        active = [r for r in rows if r["program"] != "off"]
        ranked = sorted((r for r in rows if r["queue_length_m"]), key=lambda r: r["queue_length_m"], reverse=True)
        summary = {
            "total_signals": len(rows),
            "active_signals": len(active),
            "programs_in_use": dict(Counter(r["program"] for r in rows)),
            "effectively_fixed_time": sum(
                1 for t in self.tls_ids
                if self.static[t]["programs"].get(data.get(t, {}).get("program"), {}).get("effectively_fixed")),
            "signals_with_queue": sum(1 for r in rows if r["queued_vehicles"]),
            "average_remaining_s": (sum(r["remaining_s"] for r in active) / len(active)) if active else None,
            "most_loaded_signals": [
                {k: r[k] for k in ("tls_id", "phase", "state", "queued_vehicles", "queue_length_m", "remaining_s")}
                for r in ranked[: self.top_n]
            ],
        }
        return summary, rows
