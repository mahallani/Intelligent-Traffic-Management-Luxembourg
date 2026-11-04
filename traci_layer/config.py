"""
Configuration of the TraCI data-collection layer.

Two configuration objects are defined here:

* :class:`SumoConfig`      -> HOW SUMO is launched (scenario, GUI, seed, saved state...)
* :class:`CollectorConfig` -> WHAT is collected and HOW OFTEN

Paths are resolved relative to the project root so that the code works on every
team member's machine (Windows or Linux) without editing absolute paths.

Environment variables (optional):

* ``LUST_SCENARIO_DIR`` - overrides the location of ``LuSTScenario/scenario``
* ``SUMO_HOME``         - standard SUMO variable, used to find the ``sumo`` binary
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

#: Root of the repository (``Intelligent-Traffic-Management-Luxembourg``).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

#: Default folder of the LuST scenario (ignored by Git, installed with setup_lust.ps1).
LUST_SCENARIO_DIR: Path = Path(
    os.environ.get("LUST_SCENARIO_DIR", PROJECT_ROOT / "LuSTScenario" / "scenario")
)

#: The configuration used by the project (actuated traffic lights, DUA routes).
DEFAULT_SUMOCFG: Path = LUST_SCENARIO_DIR / "dua.actuated.sumocfg"

#: Project-owned additional files (we never modify LuST itself).
PROJECT_ADDITIONAL_DIR: Path = PROJECT_ROOT / "sumo" / "additional"
EMERGENCY_VTYPES_FILE: Path = PROJECT_ADDITIONAL_DIR / "emergency_vtypes.add.xml"

#: Default output folder for exports.
DEFAULT_OUTPUT_DIR: Path = PROJECT_ROOT / "data" / "observations"

# Windows default installation path (SUMO 1.27.1 installer)
_WINDOWS_SUMO_BIN = Path(r"C:\Program Files (x86)\Eclipse\Sumo\bin")


def find_sumo_binary(gui: bool = False) -> str:
    """Return the path of ``sumo`` / ``sumo-gui``.

    Resolution order: ``$SUMO_HOME/bin`` -> ``PATH`` -> default Windows install folder.
    """
    name = "sumo-gui" if gui else "sumo"
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = []
    if os.environ.get("SUMO_HOME"):
        candidates.append(Path(os.environ["SUMO_HOME"]) / "bin" / exe)
    which = shutil.which(name)
    if which:
        candidates.append(Path(which))
    candidates.append(_WINDOWS_SUMO_BIN / exe)
    for cand in candidates:
        if cand.exists():
            return str(cand)
    # Let SUMO/TraCI raise a clear error later if it really is not installed.
    return name


@dataclass
class SumoConfig:
    """How to launch SUMO.

    Attributes
    ----------
    sumocfg:
        The ``.sumocfg`` file. Defaults to LuST ``dua.actuated.sumocfg``.
    gui:
        ``True`` -> ``sumo-gui`` (useful for demos, slower).
    use_libsumo:
        Run SUMO in-process with ``libsumo`` (same API as TraCI, 5-10x faster,
        no GUI). Falls back to TraCI if libsumo cannot be imported.
    begin / end:
        Optional simulation begin / end time in seconds (override the sumocfg).
        LuST covers 0 s (00:00) to 86400 s (24:00). Morning peak ~ 28800 s (08:00).
    load_state:
        A SUMO state file (``.xml.gz``) saved earlier with
        :meth:`SimulationController.save_state`. All scenarios S0..S4 should start
        from the SAME state to be comparable.
    seed:
        Random seed. SUMO is deterministic by default (seed 23423); fix it
        explicitly when comparing scenarios.
    output_dir:
        If set, SUMO's own outputs (summary, tripinfo, log) are redirected here
        instead of being written in the LuST folder - required when several
        scenario runs happen in parallel.
    emission_device:
        Adds ``--device.emissions.probability 1`` so that the tripinfo output also
        contains per-trip emissions. NOT needed for TraCI emission getters.
    additional_files:
        Extra additional files loaded on top of the sumocfg ones
        (e.g. the project's emergency vehicle types).
    extra_args:
        Any other SUMO command-line options.
    label:
        TraCI connection label (allows several simultaneous simulations).
    """

    sumocfg: Path = DEFAULT_SUMOCFG
    gui: bool = False
    use_libsumo: bool = False
    begin: Optional[float] = None
    end: Optional[float] = None
    load_state: Optional[Path] = None
    seed: Optional[int] = None
    output_dir: Optional[Path] = None
    emission_device: bool = False
    additional_files: Sequence[Path] = field(default_factory=list)
    extra_args: Sequence[str] = field(default_factory=list)
    save_state_rng: bool = True
    quiet: bool = True
    label: str = "default"

    def build_command(self) -> list[str]:
        """Build the SUMO command line (list form, Windows-safe)."""
        sumocfg = Path(self.sumocfg)
        if not sumocfg.exists():
            raise FileNotFoundError(
                f"SUMO configuration not found: {sumocfg}\n"
                "Run setup_lust.ps1 or set the LUST_SCENARIO_DIR environment variable."
            )
        cmd = [find_sumo_binary(self.gui), "-c", str(sumocfg)]
        if self.begin is not None:
            cmd += ["--begin", str(self.begin)]
        if self.end is not None:
            cmd += ["--end", str(self.end)]
        if self.load_state is not None:
            from .simulation import state_time

            cmd += ["--load-state", str(self.load_state)]
            t0 = state_time(self.load_state)
            if self.begin is None and t0 is not None:
                cmd += ["--begin", str(t0)]  # avoids the 'different begin time' warning
        if self.seed is not None:
            cmd += ["--seed", str(self.seed)]
        if self.output_dir is not None:
            out = Path(self.output_dir)
            out.mkdir(parents=True, exist_ok=True)
            cmd += [
                "--summary-output", str(out / "summary.xml"),
                "--tripinfo-output", str(out / "tripinfo.xml"),
                "--log", str(out / "sumo.log"),
            ]
        if self.save_state_rng:
            cmd += ["--save-state.rng", "true"]  # saved states also restore random generators
        if self.emission_device:
            cmd += ["--device.emissions.probability", "1"]
        if self.additional_files:
            # SUMO replaces the sumocfg list when --additional-files is given on the
            # command line, so we must repeat the sumocfg ones.
            base = _read_cfg_list(sumocfg, "additional-files")
            files = [str((sumocfg.parent / f).resolve()) for f in base]
            files += [str(Path(f).resolve()) for f in self.additional_files]
            cmd += ["--additional-files", ",".join(files)]
        if self.quiet:
            cmd += ["--no-step-log", "true", "--verbose", "false", "--no-warnings", "true"]
        if self.gui:
            cmd += ["--start", "true", "--quit-on-end", "true"]
        cmd += list(self.extra_args)
        return cmd


def _read_cfg_list(sumocfg: Path, option: str) -> list[str]:
    """Read a comma-separated option (e.g. ``route-files``) from a .sumocfg file."""
    import xml.etree.ElementTree as ET

    root = ET.parse(sumocfg).getroot()
    for el in root.iter(option):
        value = el.get("value", "")
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def cfg_route_files(sumocfg: Path) -> list[Path]:
    """Absolute paths of the route files declared in a .sumocfg."""
    sumocfg = Path(sumocfg)
    return [(sumocfg.parent / f).resolve() for f in _read_cfg_list(sumocfg, "route-files")]


@dataclass
class CollectorConfig:
    """What the :class:`~traci_layer.collector.TrafficDataCollector` collects.

    Per-step tracking (departures, arrivals, travel times, cumulated waiting time and
    emissions, bus stop events, emergency vehicles) ALWAYS runs at every step because
    those values are only available during the step in which they happen.

    The heavier network snapshot (edges, lanes, traffic lights) is produced every
    ``snapshot_interval`` seconds by :meth:`TrafficDataCollector.observe`.
    """

    snapshot_interval: float = 60.0
    collect_edges: bool = True
    #: "tls" = only lanes controlled by a traffic light (default, ~1 500 lanes in LuST),
    #: "all" = every lane (8 622 in LuST), None = no lane collection.
    lane_scope: Optional[str] = "tls"
    collect_traffic_lights: bool = True
    collect_buses: bool = True
    collect_emergency: bool = True
    #: Convert positions of buses / emergency vehicles to lon/lat (WGS84).
    geo_positions: bool = True
    #: Keep the per-vehicle / edge / lane / TLS rows of EVERY observation (for CSV export).
    #: The rows of the last observation are always available in ``collector.latest_tables``.
    include_details: bool = False
    #: TraCI speed-up: integrate only CO2/NOx/fuel per step (see vehicle_data.STEP_VARS_LIGHT).
    light_step_vars: bool = False
    #: Number of worst edges reported as bottlenecks in each observation.
    top_n_bottlenecks: int = 10

    # --- thresholds of DERIVED metrics (our definitions, not SUMO values) ---
    #: SUMO's own definition of a halting vehicle (m/s).
    halting_speed: float = 0.1
    #: Congestion index = 1 - mean_speed / allowed_speed. Level thresholds:
    congestion_thresholds: tuple[float, float, float] = (0.3, 0.5, 0.75)  # light / heavy / severe
    #: An edge is "congested" if its congestion index >= this value.
    congested_edge_index: float = 0.5
    #: A bus pair is "bunched" if observed headway < ratio * planned headway.
    bunching_ratio: float = 0.5

    # --- identification rules ---
    #: Vehicle types considered as emergency vehicles (besides vClass "emergency").
    emergency_type_ids: tuple[str, ...] = ("emergency", "emergency_bluelight", "emergency_plain")
    #: Route files holding the bus lines (auto-detected from the sumocfg if None).
    bus_route_files: Optional[Sequence[Path]] = None
