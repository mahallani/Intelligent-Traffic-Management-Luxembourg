"""
Traffic-light ACTUATORS - the TraCI operations the Intervention Agent will use to apply
strategies S1..S4 **inside SUMO** (never on real Luxembourg signals).

Verified TraCI setters (SUMO 1.27.1, ``traci.trafficlight``):

=========================  ===============================================================
setPhase(tls, index)        jump to a phase of the current program
setPhaseDuration(tls, s)    set the REMAINING duration of the current phase (extend/cut green)
setProgram(tls, programID)  switch to another loaded program (e.g. "1" from tll.static.xml, "off")
setRedYellowGreenState      impose a raw state string (creates an "online" program)
setProgramLogic(tls, Logic) install a new/optimised program (new cycle, splits, minDur/maxDur)
setParameter(tls, k, v)     tune actuated parameters (e.g. "max-gap", "detector-gap")
=========================  ===============================================================

This module only provides safe, logged primitives. The strategy logic (when to extend,
which bus to favour...) belongs to the Intervention Agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ActuationRecord:
    time: float
    tls_id: str
    action: str
    value: Any


class TrafficLightActuator:
    """Logged wrappers around the TraCI traffic-light setters."""

    def __init__(self, api: Any):
        self.api = api
        self.log: list[ActuationRecord] = []
        self._original_program: dict[str, str] = {}

    def _record(self, tls_id: str, action: str, value: Any) -> None:
        self._original_program.setdefault(tls_id, self.api.trafficlight.getProgram(tls_id))
        self.log.append(ActuationRecord(self.api.simulation.getTime(), tls_id, action, value))

    # ----------------------------------------------------------------- primitives
    def set_phase(self, tls_id: str, phase_index: int) -> None:
        self._record(tls_id, "set_phase", phase_index)
        self.api.trafficlight.setPhase(tls_id, phase_index)

    def set_phase_duration(self, tls_id: str, remaining_s: float) -> None:
        self._record(tls_id, "set_phase_duration", remaining_s)
        self.api.trafficlight.setPhaseDuration(tls_id, remaining_s)

    def set_program(self, tls_id: str, program_id: str) -> None:
        self._record(tls_id, "set_program", program_id)
        self.api.trafficlight.setProgram(tls_id, program_id)

    def set_state(self, tls_id: str, state: str) -> None:
        self._record(tls_id, "set_state", state)
        self.api.trafficlight.setRedYellowGreenState(tls_id, state)

    def set_program_logic(self, tls_id: str, logic: Any) -> None:
        self._record(tls_id, "set_program_logic", getattr(logic, "programID", None))
        self.api.trafficlight.setProgramLogic(tls_id, logic)

    def restore(self, tls_id: Optional[str] = None) -> None:
        """Return to the program that was active before our first action."""
        targets = [tls_id] if tls_id else list(self._original_program)
        for t in targets:
            prog = self._original_program.get(t)
            if prog is not None:
                self.api.trafficlight.setProgram(t, prog)
                self.log.append(ActuationRecord(self.api.simulation.getTime(), t, "restore", prog))

    # ------------------------------------------------------------- helpers
    def link_indices_of_lane(self, tls_id: str, lane_id: str) -> list[int]:
        """Signal indices (positions in the state string) whose incoming lane is ``lane_id``."""
        links = self.api.trafficlight.getControlledLinks(tls_id)
        return [i for i, group in enumerate(links) if any(l[0] == lane_id for l in group)]

    def phases_serving_lane(self, tls_id: str, lane_id: str) -> list[int]:
        """Indices of the current program's phases giving green (G/g) to ``lane_id``."""
        idx = self.link_indices_of_lane(tls_id, lane_id)
        program = self.api.trafficlight.getProgram(tls_id)
        for logic in self.api.trafficlight.getAllProgramLogics(tls_id):
            if logic.programID == program:
                return [i for i, p in enumerate(logic.phases)
                        if any(p.state[j] in "Gg" for j in idx)]
        return []

    def extend_green(self, tls_id: str, lane_id: str, extra_s: float, max_remaining_s: float = 60.0) -> bool:
        """If ``lane_id`` currently has green, extend the current phase by ``extra_s``.

        The remaining green is capped at ``max_remaining_s`` and is never shortened.
        Returns True if the extension was applied. Typical use: bus / emergency vehicle
        approaching the stop line (S1 / S2).
        """
        tl = self.api.trafficlight
        state = tl.getRedYellowGreenState(tls_id)
        if not any(state[i] in "Gg" for i in self.link_indices_of_lane(tls_id, lane_id)):
            return False
        remaining = tl.getNextSwitch(tls_id) - self.api.simulation.getTime()
        target = min(remaining + extra_s, max_remaining_s)
        if target <= remaining:  # cap already reached: never shorten a green we meant to extend
            return False
        self.set_phase_duration(tls_id, target)
        return True
