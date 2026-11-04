"""
Simulation-level control and status.

Everything here is DIRECTLY available through ``traci.simulation`` - no derived metric.

The *ID lists* (departed / arrived / teleporting...) only describe the LAST step, so they
must be read at every step: :class:`SimulationController.step` does exactly that and keeps
the result in :attr:`SimulationController.last_events`.
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _open_text(path: Path, mode: str = "rt"):
    return gzip.open(path, mode, encoding="utf-8") if path.suffix == ".gz" else open(path, mode, encoding="utf-8")


def repair_state_file(path: Path | str) -> int:
    """Fix a SUMO 1.27.1 state file so that it can be loaded again.

    Verified on LuST: SUMO 1.27.1 writes ``state=""`` for every *actuated* traffic light
    in a saved state, and then refuses to load it ("Attribute 'state' in definition of
    tlLogic ... is empty"). Removing the empty attribute restores the normal behaviour
    (program, phase and remaining duration are kept). Returns the number of fixes.
    """
    path = Path(path)
    with _open_text(path) as fh:
        text = fh.read()
    fixed, n = re.subn(r'(<tlLogic\b[^>]*?) state=""', r"\1", text)
    if n:
        with _open_text(path, "wt") as fh:
            fh.write(fixed)
    return n


def state_time(path: Path | str) -> Optional[float]:
    """Simulation time stored in a state file (``<snapshot time=...>``)."""
    with _open_text(Path(path)) as fh:
        head = fh.read(4096)
    match = re.search(r'<snapshot[^>]*\btime="([0-9.]+)"', head)
    return float(match.group(1)) if match else None


@dataclass
class StepEvents:
    """Events that happened during the last simulation step (TraCI ``simulation`` domain)."""

    time: float = 0.0
    departed: tuple[str, ...] = ()          # getDepartedIDList()
    arrived: tuple[str, ...] = ()           # getArrivedIDList()
    teleport_started: tuple[str, ...] = ()  # getStartingTeleportIDList()
    colliding: tuple[str, ...] = ()         # getCollidingVehiclesIDList()
    emergency_stopping: tuple[str, ...] = ()  # getEmergencyStoppingVehiclesIDList()


@dataclass
class SimulationCounters:
    """Running totals since the collector started."""

    departed: int = 0
    arrived: int = 0
    teleports: int = 0
    collisions: int = 0
    emergency_stops: int = 0
    vehicle_seconds: float = 0.0   # sum over steps of (running vehicles * dt) -> VHT
    teleported_ids: set = field(default_factory=set)


class SimulationController:
    """Thin wrapper around ``traci.simulation`` used by the collector and the agents."""

    def __init__(self, api: Any):
        self.api = api
        self.step_length: float = api.simulation.getDeltaT()   # s (LuST: 1 s)
        self.last_events = StepEvents(time=api.simulation.getTime())
        self.counters = SimulationCounters()

    # ------------------------------------------------------------------- stepping
    @property
    def time(self) -> float:
        """Current simulation time in seconds (``simulation.getTime``)."""
        return self.api.simulation.getTime()

    def step(self) -> StepEvents:
        """Advance one step and record the events of that step."""
        sim = self.api.simulation
        self.api.simulationStep()
        ev = StepEvents(
            time=sim.getTime(),
            departed=tuple(sim.getDepartedIDList()),
            arrived=tuple(sim.getArrivedIDList()),
            teleport_started=tuple(sim.getStartingTeleportIDList()),
            colliding=tuple(sim.getCollidingVehiclesIDList()),
            emergency_stopping=tuple(sim.getEmergencyStoppingVehiclesIDList()),
        )
        c = self.counters
        c.departed += len(ev.departed)
        c.arrived += len(ev.arrived)
        c.teleports += len(ev.teleport_started)
        c.teleported_ids.update(ev.teleport_started)
        c.collisions += len(ev.colliding)
        c.emergency_stops += len(ev.emergency_stopping)
        self.last_events = ev
        return ev

    def has_pending_traffic(self) -> bool:
        """True while vehicles are running or still waiting to be inserted."""
        return self.api.simulation.getMinExpectedNumber() > 0

    # -------------------------------------------------------------------- status
    def status(self, running_vehicles: int) -> dict:
        """Simulation status block of an observation."""
        sim = self.api.simulation
        c = self.counters
        return {
            "time": self.time,
            "step_length": self.step_length,
            "running_vehicles": running_vehicles,              # vehicle.getIDCount()
            "pending_vehicles": len(sim.getPendingVehicles()),  # waiting for insertion
            "min_expected_vehicles": sim.getMinExpectedNumber(),
            "departed_last_step": len(self.last_events.departed),
            "arrived_last_step": len(self.last_events.arrived),
            "departed_total": c.departed,
            "arrived_total": c.arrived,
            "teleports_total": c.teleports,
            "collisions_total": c.collisions,
            "emergency_braking_total": c.emergency_stops,
        }

    # ----------------------------------------------------------- state snapshots
    def save_state(self, path: Path | str) -> Path:
        """Save the complete simulation state (``simulation.saveState``).

        Use it to freeze the network at the moment an incident is detected, then
        start S0..S4 from that file with ``SumoConfig(load_state=...)`` so that all
        strategies are compared from the same initial conditions.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.api.simulation.saveState(str(path))
        repair_state_file(path)  # SUMO 1.27.1 actuated-TLS workaround (see function doc)
        return path

    def load_state(self, path: Path | str) -> None:
        """Load a state in the running simulation (``simulation.loadState``)."""
        self.api.simulation.loadState(str(path))

    def to_geo(self, x: float, y: float) -> tuple[float, float]:
        """Network (x, y) -> (lon, lat) WGS84 (``simulation.convertGeo``)."""
        lon, lat = self.api.simulation.convertGeo(x, y)
        return lon, lat
