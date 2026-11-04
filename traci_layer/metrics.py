"""
DERIVED metrics - pure Python, no TraCI call.

Everything in this module is a metric that **SUMO does not provide directly** and that
we compute ourselves from raw TraCI values. Keeping the definitions here (and unit
tested) means every agent uses exactly the same definition.

Unit conventions used across the layer
--------------------------------------
* speed            : m/s internally, km/h in summaries (``*_kmh``)
* time             : s
* distance / queue : m
* occupancy        : % (0-100). NB: SUMO 1.27.1 returns a fraction 0-1 (despite its
                     docstring); edge_data / lane_data multiply by 100
* emissions        : TraCI returns mg/s; cumulated values are reported in g or kg
* fuel             : TraCI returns mg/s (mass, not volume); reported in g / kg
"""
from __future__ import annotations

import math
import statistics
from typing import Iterable, Optional, Sequence

MS_TO_KMH = 3.6
MG_TO_G = 1e-3
MG_TO_KG = 1e-6

#: Density used ONLY to give an indicative volume of fuel (petrol, kg/L).
#: SUMO reports fuel as a mass. This is an assumption, keep the mass for decisions.
PETROL_DENSITY_KG_PER_L = 0.745


def kmh(speed_ms: Optional[float]) -> Optional[float]:
    """m/s -> km/h (None-safe)."""
    return None if speed_ms is None else speed_ms * MS_TO_KMH


def safe_mean(values: Iterable[float]) -> Optional[float]:
    """Mean of an iterable, ``None`` if it is empty."""
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    """Linear-interpolated percentile (q in 0..100), ``None`` if empty."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def coefficient_of_variation(values: Sequence[float]) -> Optional[float]:
    """Std / mean. Used for bus headway regularity (0 = perfectly regular)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    m = statistics.fmean(vals)
    return statistics.pstdev(vals) / m if m > 0 else None


# ----------------------------------------------------------------- congestion
def congestion_index(mean_speed: float, allowed_speed: float) -> float:
    """Congestion index in [0, 1] = 1 - mean_speed / allowed_speed.

    0 = free flow, 1 = standstill. Our definition (Cette métrique doit être calculée).
    """
    if allowed_speed <= 0:
        return 0.0
    return min(1.0, max(0.0, 1.0 - mean_speed / allowed_speed))


def congestion_level(index: Optional[float], thresholds: tuple[float, float, float] = (0.3, 0.5, 0.75)) -> str:
    """Map a congestion index to a label: free / light / heavy / severe."""
    if index is None:
        return "unknown"
    light, heavy, severe = thresholds
    if index >= severe:
        return "severe"
    if index >= heavy:
        return "heavy"
    if index >= light:
        return "light"
    return "free"


def queue_from_vehicles(
    lane_length: float,
    vehicles: Sequence[tuple[float, float, float]],
    halting_speed: float = 0.1,
    max_gap: float = 10.0,
) -> tuple[int, float]:
    """Queue at the downstream end (stop line) of a lane.

    Parameters
    ----------
    lane_length:
        Lane length (m).
    vehicles:
        ``(lane_position_m, speed_ms, vehicle_length_m)`` of every vehicle on the lane.
        ``lane_position`` is the position of the vehicle FRONT measured from the lane start.
    max_gap:
        Maximum empty space (m) between the stop line and the first halted vehicle, and
        between two consecutive halted vehicles, for them to belong to the same queue.

    Returns
    -------
    (queued_vehicles, queue_length_m)
        The queue is the contiguous platoon of halting vehicles (speed < ``halting_speed``)
        starting at the stop line. Queue length = distance from the stop line to the rear
        bumper of the last vehicle of that platoon. Halted vehicles far from the stop line
        (bus stop, vehicle blocked mid-lane) do not form a stop-line queue.

    Notes
    -----
    SUMO has no lane-level "queue length" getter (only E2 detectors provide
    ``getJamLengthMeters`` and LuST has none) -> Cette métrique doit être calculée.
    """
    ordered = sorted(vehicles, key=lambda v: v[0], reverse=True)  # closest to stop line first
    n, boundary = 0, lane_length          # boundary = rear of the queue so far
    for pos, speed, length in ordered:
        if speed >= halting_speed or boundary - pos > max_gap:
            break
        n += 1
        boundary = pos - length
    return n, (max(0.0, lane_length - boundary) if n else 0.0)


def estimated_queue_length(halting_number: int, mean_vehicle_length: float, min_gap: float = 2.5) -> float:
    """Fallback queue estimate (m) = halting vehicles * (mean length + gap)."""
    if halting_number <= 0:
        return 0.0
    return halting_number * (max(mean_vehicle_length, 0.0) + min_gap)


# ----------------------------------------------------------------- buses
def headways(times: Sequence[float]) -> list[float]:
    """Successive differences of sorted event times (s)."""
    ts = sorted(times)
    return [b - a for a, b in zip(ts, ts[1:])]


def is_bunched(observed_headway: float, planned_headway: Optional[float], ratio: float = 0.5) -> bool:
    """True if a bus arrives less than ``ratio * planned headway`` after the previous one."""
    if planned_headway is None or planned_headway <= 0:
        return False
    return observed_headway < ratio * planned_headway


# ----------------------------------------------------------------- emissions
def integrate(rate_mg_per_s: float, dt: float) -> float:
    """mg/s * s -> mg (TraCI emission getters return the rate of the last step)."""
    return rate_mg_per_s * dt


def free_flow_time(edge_lengths_and_speeds: Iterable[tuple[float, float]], vehicle_max_speed: Optional[float] = None) -> float:
    """Ideal travel time (s) on a route = sum(length / min(allowed, vehicle max speed))."""
    total = 0.0
    for length, speed in edge_lengths_and_speeds:
        v = speed if vehicle_max_speed is None else min(speed, vehicle_max_speed)
        if v > 0:
            total += length / v
    return total
