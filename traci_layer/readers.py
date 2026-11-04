"""
Efficient bulk reading of TraCI variables - transport-aware.

Measured on LuST at 07:00 (~3 900 vehicles, SUMO 1.27.1, one SUMO step = 34 ms):

=====================================================  =============================
approach                                               cost
=====================================================  =============================
TraCI per-vehicle subscription, 16 variables           +182 ms per step
TraCI context subscription, 11 variables               +100 ms per step
TraCI context subscription, 6 variables                 +69 ms per step
libsumo direct getters, 11 variables                    +29 ms per step
TraCI permanent subscription of all 5 779 edges        +136 ms per step (+11 s setup)
TraCI one-shot context subscription of all edges         0.45 s per snapshot
=====================================================  =============================

Hence the strategy implemented here:

* TraCI (sockets): the per-step vehicle stream uses ONE persistent *context subscription*
  (all vehicles within 10 000 km of an anchor junction = whole network) - no per-vehicle
  subscribe call. Edges / lanes / vehicle details needed only at snapshot time are read
  with a *one-shot* context subscription (``begin = end = now``), which expires by itself.
* libsumo (in-process): plain getters, which cost ~0.4 µs per call.

All functions return ``{object_id: {var_code: value}}``.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import traci.constants as tc

#: TraCI variable code -> getter name, per domain (used with libsumo and as fallback).
GETTERS: dict[str, dict[int, str]] = {
    "vehicle": {
        tc.VAR_POSITION: "getPosition", tc.VAR_ROAD_ID: "getRoadID", tc.VAR_LANE_ID: "getLaneID",
        tc.VAR_LANEPOSITION: "getLanePosition", tc.VAR_SPEED: "getSpeed", tc.VAR_ACCELERATION: "getAcceleration",
        tc.VAR_WAITING_TIME: "getWaitingTime", tc.VAR_ACCUMULATED_WAITING_TIME: "getAccumulatedWaitingTime",
        tc.VAR_TIMELOSS: "getTimeLoss", tc.VAR_DISTANCE: "getDistance",
        tc.VAR_CO2EMISSION: "getCO2Emission", tc.VAR_COEMISSION: "getCOEmission", tc.VAR_HCEMISSION: "getHCEmission",
        tc.VAR_PMXEMISSION: "getPMxEmission", tc.VAR_NOXEMISSION: "getNOxEmission",
        tc.VAR_FUELCONSUMPTION: "getFuelConsumption", tc.VAR_STOPSTATE: "getStopState",
    },
    "edge": {
        tc.LAST_STEP_VEHICLE_NUMBER: "getLastStepVehicleNumber", tc.LAST_STEP_MEAN_SPEED: "getLastStepMeanSpeed",
        tc.LAST_STEP_OCCUPANCY: "getLastStepOccupancy", tc.LAST_STEP_VEHICLE_HALTING_NUMBER: "getLastStepHaltingNumber",
        tc.LAST_STEP_LENGTH: "getLastStepLength", tc.VAR_CURRENT_TRAVELTIME: "getTraveltime",
        tc.VAR_WAITING_TIME: "getWaitingTime", tc.VAR_CO2EMISSION: "getCO2Emission",
        tc.VAR_NOXEMISSION: "getNOxEmission", tc.VAR_FUELCONSUMPTION: "getFuelConsumption",
        tc.LAST_STEP_VEHICLE_ID_LIST: "getLastStepVehicleIDs",
    },
    "lane": {
        tc.LAST_STEP_VEHICLE_NUMBER: "getLastStepVehicleNumber", tc.LAST_STEP_MEAN_SPEED: "getLastStepMeanSpeed",
        tc.LAST_STEP_OCCUPANCY: "getLastStepOccupancy", tc.LAST_STEP_VEHICLE_HALTING_NUMBER: "getLastStepHaltingNumber",
        tc.LAST_STEP_LENGTH: "getLastStepLength", tc.VAR_WAITING_TIME: "getWaitingTime",
        tc.LAST_STEP_VEHICLE_ID_LIST: "getLastStepVehicleIDs", tc.VAR_CURRENT_TRAVELTIME: "getTraveltime",
    },
    "trafficlight": {
        tc.TL_RED_YELLOW_GREEN_STATE: "getRedYellowGreenState", tc.TL_CURRENT_PHASE: "getPhase",
        tc.TL_CURRENT_PROGRAM: "getProgram", tc.TL_PHASE_DURATION: "getPhaseDuration",
        tc.TL_NEXT_SWITCH: "getNextSwitch", tc.TL_SPENT_DURATION: "getSpentDuration",
    },
}

_CONTEXT_DOMAIN = {
    "vehicle": tc.CMD_GET_VEHICLE_VARIABLE,
    "edge": tc.CMD_GET_EDGE_VARIABLE,
    "lane": tc.CMD_GET_LANE_VARIABLE,
}
_WHOLE_NETWORK = 1.0e7  # m - context range covering any SUMO network


def is_libsumo(api: Any) -> bool:
    return getattr(api, "__name__", "") == "libsumo"


class BulkReader:
    def __init__(self, api: Any):
        self.api = api
        self.libsumo = is_libsumo(api)
        junctions = [j for j in api.junction.getIDList() if not j.startswith(":")]
        if len(junctions) < 4:
            junctions = (junctions * 4)[:4] if junctions else []
        # distinct anchors so that context subscriptions never replace each other
        self._anchor = {"stream": junctions[0], "vehicle": junctions[1], "edge": junctions[2], "lane": junctions[3]}
        self._stream_codes: list[int] = []

    # ------------------------------------------------------------ vehicle stream
    def start_vehicle_stream(self, codes: Iterable[int]) -> None:
        """Persistent per-step reading of ``codes`` for ALL vehicles."""
        self._stream_codes = list(codes)
        if not self.libsumo:
            self.api.junction.subscribeContext(self._anchor["stream"], tc.CMD_GET_VEHICLE_VARIABLE,
                                               _WHOLE_NETWORK, self._stream_codes)

    def read_vehicle_stream(self) -> dict[str, dict[int, Any]]:
        if self.libsumo:
            return self._getters("vehicle", self.api.vehicle.getIDList(), self._stream_codes)
        return dict(self.api.junction.getContextSubscriptionResults(self._anchor["stream"]) or {})

    # ------------------------------------------------------------- one-shot
    def read_once(self, domain: str, codes: Iterable[int], ids: Optional[Iterable[str]] = None) -> dict[str, dict[int, Any]]:
        """Read ``codes`` for all objects of ``domain`` (or only ``ids``) at the current step."""
        codes = list(codes)
        if self.libsumo or domain not in _CONTEXT_DOMAIN:
            obj_ids = list(ids) if ids is not None else getattr(self.api, domain).getIDList()
            return self._getters(domain, obj_ids, codes)
        now = self.api.simulation.getTime()
        anchor = self._anchor[domain]
        self.api.junction.subscribeContext(anchor, _CONTEXT_DOMAIN[domain], _WHOLE_NETWORK, codes, now, now)
        res = self.api.junction.getContextSubscriptionResults(anchor) or {}
        if ids is None:
            return dict(res)
        wanted = set(ids)
        return {k: v for k, v in res.items() if k in wanted}

    def _getters(self, domain: str, ids: Iterable[str], codes: list[int]) -> dict[str, dict[int, Any]]:
        dom = getattr(self.api, domain)
        funcs = [(c, getattr(dom, GETTERS[domain][c])) for c in codes]
        return {i: {c: f(i) for c, f in funcs} for i in ids}
