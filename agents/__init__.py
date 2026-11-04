"""
Multi-agent traffic management - Kirchberg 4-signal scenario (SUMO / TraCI).

Agents (one package each), run in this order at every simulation step by agents.orchestrator:
    observation.CollectionAgent   -> reads the simulation (queues, phases, vehicles) through TraCI
    detection.DetectionAgent      -> flags persistent congestion / suspected incidents per lane
    prediction.PredictionAgent    -> short-horizon queue forecast per intersection (simulation only)
    decision.*Controller          -> chooses keep / advance for each signal (fixed, max-pressure, Q-learning RL)
    intervention.TLSActuator      -> applies the decision safely (min/max green, yellow always kept)

Everything produced here is SIMULATED data (data_origin = "SIMULATED_sumo_lust_kirchberg_4tls").
It is never mixed with the real CITA / PCH / GTFS datasets.
"""
DATA_ORIGIN = "SIMULATED_sumo_lust_kirchberg_4tls"
