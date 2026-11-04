"""
traci_layer - SUMO/TraCI observation & data-collection layer of the
Intelligent Multi-Agent Traffic Management project (LuST Luxembourg).

    SUMO -> SumoConnection -> TrafficDataCollector -> Observation Agent -> ... -> Decision Agent

Why ``traci_layer`` and not ``traci/``? A project package called ``traci`` would
collide with the official ``traci`` library as soon as somebody adds an
``__init__.py`` to it or imports it from the project root. The historical
``traci/test_lust.py`` script is kept untouched.
"""
from .actuators import TrafficLightActuator
from .collector import TrafficDataCollector, clock
from .config import (DEFAULT_OUTPUT_DIR, DEFAULT_SUMOCFG, EMERGENCY_VTYPES_FILE, LUST_SCENARIO_DIR,
                     PROJECT_ROOT, CollectorConfig, SumoConfig)
from .connection import SumoConnection
from .emergency_data import EmergencyVehicleSpec, spawn_emergency_vehicle
from .export import RunExporter, observations_to_dataframe, read_jsonl, write_json
from .kpi import KPI_DIRECTIONS, ScenarioKPIs, compare_scenarios
from .network import NetworkTopology
from .report import format_kpis, format_observation

__version__ = "1.0.0"

__all__ = [
    "SumoConfig", "CollectorConfig", "SumoConnection", "TrafficDataCollector",
    "TrafficLightActuator", "EmergencyVehicleSpec", "spawn_emergency_vehicle",
    "RunExporter", "observations_to_dataframe", "read_jsonl", "write_json",
    "ScenarioKPIs", "KPI_DIRECTIONS", "compare_scenarios", "NetworkTopology",
    "format_observation", "format_kpis", "clock",
    "PROJECT_ROOT", "LUST_SCENARIO_DIR", "DEFAULT_SUMOCFG", "EMERGENCY_VTYPES_FILE", "DEFAULT_OUTPUT_DIR",
]
