"""Data-quality tests: builder logic on synthetic data + validation of the produced *_v1 datasets.
Run:  python -m pytest -p no:cacheprovider tests/test_data_quality.py -q"""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "data_pipeline"))
import common  # noqa: E402
import build_cita_traffic_v1 as bt  # noqa: E402
import build_cita_events_v1 as be  # noqa: E402
import build_task_datasets_v1 as bk  # noqa: E402
import validate_datasets as vd  # noqa: E402


# ---------- common helpers
def test_separator_detection_and_column_validation(tmp_path):
    for sep in (",", ";", "\t", "|"):
        f = tmp_path / f"x{ord(sep)}.csv"
        f.write_text(sep.join(["a", "b", "c"]) + "\n1" + sep + "2" + sep + "\n", encoding="utf-8")
        d = common.read_csv_checked(f, expected_columns=["a", "b", "c"])
        assert d.attrs["separator"] == sep and pd.isna(d.c[0]) and d.a[0] == "1"
    with pytest.raises(ValueError):
        common.read_csv_checked(tmp_path / "x44.csv", expected_columns=["a", "b"])


def test_safe_path_never_overwrites(tmp_path):
    f = tmp_path / "out.csv"
    f.write_text("keep", encoding="utf-8")
    with pytest.raises(common.OutputExists):
        common.write_csv(pd.DataFrame({"a": [1]}), f)
    assert f.read_text(encoding="utf-8") == "keep"


# ---------- traffic dedup / flags
def _traffic_rows():
    base = {c: None for c in bt.VALUE_COLS}
    base.update(speed_kmh="90", occupancy_percent="3", vehicle_flow_rate="800", flow_period_s="3600",
                latitude="49.6", longitude="6.1", direction="inbound")
    rows = []
    for i, (sid, ts, cts, speed, src) in enumerate([
            ("A1.X.1", "2026-10-10T10:00:00+02:00", "2026-10-10T08:03:00+00:00", "90", "f1"),
            ("A1.X.1", "2026-10-10T10:00:00+02:00", "2026-10-10T08:04:00+00:00", "90", "f2"),   # identical repeat
            ("A1.X.2", "2026-10-10T10:00:00+02:00", "2026-10-10T08:03:00+00:00", "80", "f1"),
            ("A1.X.2", "2026-10-10T10:00:00+02:00", "2026-10-10T08:04:00+00:00", "55", "f2")]):  # contradiction
        r = dict(base, sensor_id=sid, measurement_timestamp=ts, collection_timestamp_utc=cts, speed_kmh=speed,
                 source_file=src, collection_timestamp_origin="collector_utc_clock", road="A1")
        rows.append(r)
    return pd.DataFrame(rows)


def test_traffic_dedup_identical_vs_contradiction():
    out, st = bt.dedup_reference(_traffic_rows())
    assert st["keys_with_contradictions"] == 1
    a = out[out.sensor_id == "A1.X.1"]
    assert len(a) == 1 and a.n_sightings.iloc[0] == 2 and a.source_file.iloc[0] == "f1|f2"
    b = out[out.sensor_id == "A1.X.2"]
    assert len(b) == 2 and b._conflict.all()          # both contradictory rows kept
    flagged, counts, _ = bt.add_flags(out)
    assert counts["conflict_same_key"] == 2
    assert flagged.measurement_timestamp_utc.iloc[0].endswith("+00:00")
    assert set(flagged.speed_kmh) == {"90", "80", "55"}  # original values untouched


def test_traffic_flags_do_not_delete():
    d = _traffic_rows().iloc[[0]].copy()
    d["speed_kmh"] = "260"
    d["latitude"] = None
    out, _ = bt.dedup_reference(d)
    out, counts, _ = bt.add_flags(out)
    assert len(out) == 1 and counts["speed_implausible_gt200"] == 1 and counts["location_missing"] == 1


# ---------- events
def test_bool_normalisation_keeps_unknown():
    s = pd.Series(["True", "true", "FALSE", "", None, "peut-etre"])
    out = be.to_bool(s.replace("", None))
    assert out.tolist()[:3] == [True, True, False]
    assert out.isna().tolist()[3:] == [True, True, True]


def test_event_correspondence_exact_uncertain_none():
    st = pd.DataFrame({"record_id": ["1-1", "2-1"], "creation_time": ["c1", "c2"], "overall_start_time": ["s1", "s2"],
                       "latitude": ["49.1", "49.2"], "longitude": ["6.1", "6.2"], "road_destination": ["d1", "d2"]})
    leg = pd.DataFrame({"legacy_event_uid": ["L1", "L2", "L3"], "creation_time": ["c1", "c2", "c9"],
                        "start_time": ["s1", "s2", "s9"], "latitude": ["49.1", "49.9", "49.1"],
                        "longitude": ["6.1", "6.2", "6.1"], "destination": ["d1", "d2", "d1"]})
    c = be.correspond(leg, st).set_index("legacy_event_uid")
    assert c.loc["L1", "confidence"] == "exact" and c.loc["L1", "record_id"] == "1-1"
    assert c.loc["L2", "confidence"] == "uncertain"
    assert c.loc["L3", "confidence"] == "none" and pd.isna(c.loc["L3", "record_id"])


# ---------- task B: no leakage, no gap filling
def test_task_b_lags_targets_and_split():
    ts = ["2026-10-10T08:00:00+00:00", "2026-10-10T08:05:00+00:00", "2026-10-10T08:10:00+00:00",
          "2026-10-10T08:40:00+00:00", "2026-10-10T08:45:00+00:00"]
    d = pd.DataFrame({"sensor_id": "A1.X.1", "road": "A1", "direction": "in", "measurement_timestamp_utc": ts[::-1],
                      "speed_kmh": ["50", "45", "40", "30", "20"][::-1], "occupancy_percent": "1",
                      "vehicle_flow_rate": "100", "quality_flags": ""})
    b = bk.task_b(d)
    assert b.measurement_timestamp_utc.is_monotonic_increasing
    assert pd.isna(b.lag1_speed_kmh.iloc[0]) and b.lag1_speed_kmh.iloc[1] == 50
    assert pd.isna(b.lag1_speed_kmh.iloc[3])             # after a 30-min gap: no lag
    assert b["target_speed_kmh_t+5"].iloc[0] == 45 and pd.isna(b["target_speed_kmh_t+5"].iloc[2])  # gap not filled
    assert b["target_speed_kmh_t+10"].iloc[0] == 40
    order = b.split.map({"train": 0, "validation": 1, "test": 2})
    assert order.is_monotonic_increasing


# ---------- produced datasets
def test_produced_datasets_validate():
    v = vd.V()
    for fn in (vd.validate_traffic, vd.validate_events, vd.validate_gtfs, vd.validate_tasks):
        fn(v, "v1")
    failed = [r for r in v.results if not r["passed"]]
    assert not failed, failed


def test_legacy_outputs_marked_and_kept():
    leg = common.read_csv_checked(ROOT / "data/interim/cita/cita_traffic_legacy_diagnostic_v1.csv")
    assert leg.quality_flags.str.contains("legacy_sensor_attribution_unreliable").all()
    for f in ("cita_traffic_historical.csv", "cita_traffic_historical_fixed.csv", "cita_traffic_live.csv"):
        assert (ROOT / "data/historical/cita/traffic" / f).exists()
    ref = common.read_csv_checked(ROOT / "data/processed/cita_traffic/cita_traffic_reference_v1.csv")
    assert not ref.source_file.str.contains("historical|_live").any()
