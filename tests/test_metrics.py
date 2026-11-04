"""Unit tests of the derived metrics (no SUMO needed)."""
import pytest

from traci_layer import metrics as m
from traci_layer.bus_data import line_of
from traci_layer.collector import clock
from traci_layer.export import flatten


def test_unit_conversions():
    assert m.kmh(10) == pytest.approx(36.0)
    assert m.kmh(None) is None
    assert m.integrate(1000.0, 1.0) == 1000.0  # mg/s * s


def test_congestion_index_and_levels():
    assert m.congestion_index(13.89, 13.89) == 0.0
    assert m.congestion_index(0.0, 13.89) == 1.0
    assert m.congestion_index(20.0, 13.89) == 0.0       # faster than limit -> clipped
    assert m.congestion_index(5.0, 0.0) == 0.0          # invalid limit
    assert m.congestion_level(0.1) == "free"
    assert m.congestion_level(0.35) == "light"
    assert m.congestion_level(0.6) == "heavy"
    assert m.congestion_level(0.9) == "severe"
    assert m.congestion_level(None) == "unknown"


def test_queue_contiguous_platoon_from_stop_line():
    # lane 100 m, 3 halted cars at the stop line, then a moving car
    vehicles = [(99.0, 0.0, 5.0), (92.5, 0.0, 5.0), (86.0, 0.05, 5.0), (60.0, 8.0, 5.0)]
    n, length = m.queue_from_vehicles(100.0, vehicles)
    assert n == 3
    assert length == pytest.approx(100.0 - (86.0 - 5.0))


def test_queue_ignores_vehicles_far_from_stop_line():
    # a bus halted at a mid-lane stop is not a stop-line queue
    assert m.queue_from_vehicles(300.0, [(150.0, 0.0, 12.0)]) == (0, 0.0)
    # a moving leader breaks the queue
    assert m.queue_from_vehicles(100.0, [(99.0, 5.0, 5.0), (92.0, 0.0, 5.0)]) == (0, 0.0)
    # a large hole between two halted vehicles ends the queue
    n, _ = m.queue_from_vehicles(100.0, [(99.0, 0.0, 5.0), (50.0, 0.0, 5.0)])
    assert n == 1


def test_estimated_queue():
    assert m.estimated_queue_length(0, 5.0) == 0.0
    assert m.estimated_queue_length(4, 5.0, 2.5) == pytest.approx(30.0)


def test_statistics_helpers():
    assert m.safe_mean([]) is None
    assert m.safe_mean([1, None, 3]) == 2
    assert m.percentile([1, 2, 3, 4], 50) == 2.5
    assert m.coefficient_of_variation([10, 10, 10]) == 0.0
    assert m.coefficient_of_variation([5]) is None


def test_bus_helpers():
    assert m.headways([0, 600, 1500]) == [600, 900]
    assert m.is_bunched(200, 900, 0.5) is True
    assert m.is_bunched(800, 900, 0.5) is False
    assert m.is_bunched(10, None) is False
    # LuST naming convention
    assert line_of("AVL---_12_5") == "AVL---_12"
    assert line_of("CNA____NBNA_0") == "CNA____NBNA"
    assert line_of("AVL---_CN_1_0") == "AVL---_CN_1"


def test_free_flow_time():
    assert m.free_flow_time([(100, 10), (300, 30)]) == pytest.approx(20.0)
    assert m.free_flow_time([(100, 50)], vehicle_max_speed=10) == pytest.approx(10.0)


def test_clock_and_flatten():
    assert clock(25200) == "07:00:00"
    assert clock(30661) == "08:31:01"
    assert flatten({"a": {"b": 1, "c": [1, 2]}, "d": 2}) == {"a.b": 1, "d": 2}
